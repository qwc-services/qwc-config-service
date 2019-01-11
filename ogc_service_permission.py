import os
from urllib.parse import urljoin
from xml.etree import ElementTree

from flask import json
import requests
from sqlalchemy.orm import aliased

from permission_query import PermissionQuery


class OGCServicePermission(PermissionQuery):
    """OGCServicePermission class

    Query permissions for an OGC service.
    """

    def __init__(self, default_allow, config_models, logger):
        """Constructor

        :param ConfigModels config_models: Helper for ORM models
        :param Logger logger: Application logger
        """
        super(OGCServicePermission, self).__init__(config_models, logger)

        self.default_allow = default_allow

        # get internal QGIS server URL from ENV
        # (default: local qgis-server container)
        self.qgis_server_url = os.environ.get('QGIS_SERVER_URL',
                                              'http://localhost:8001/ows/').rstrip('/') + '/'

    def permissions(self, params, username, group, session):
        """Query permissions for OGC service.

        Return OGC service permissions if available and permitted.

        :param obj params: Request parameters with
                           ows_name=<OWS service name>&ows_type=<OWS type>
        :param str username: User name
        :param str group: Group name
        :param Session session: DB session
        """
        permissions = {}

        ows_name = params.get('ows_name')
        ows_type = params.get('ows_type')

        if ows_type not in ['WMS', 'WFS']:
            # unsupported OWS type
            return permissions

        # get complete OGC service permissions from GetProjectSettings
        permissions = self.parseProjectSettings(ows_name, ows_type)
        if not permissions:
            return permissions

        permissions, map_id = self.filter_map_permissions(
            self.default_allow, ows_name, permissions, username, group, session
        )
        if map_id is None:
            return permissions
        permissions = self.filter_layer_permissions(
            self.default_allow, map_id, permissions, username, group, session
        )
        permissions = self.filter_field_permissions(
            map_id, permissions, username, group, session
        )
        permissions = self.filter_print_template_permissions(
            self.default_allow, map_id, permissions, username, group, session
        )
        # remove group_layers
        if permissions:
            permissions.pop('group_layers', None)

        return permissions

    def parseProjectSettings(self, ows_name, ows_type):
        """Get complete OGC service permissions from GetProjectSettings.

        TODO: support WFS

        :param str ows_name: OWS service name
        :param str ows_type: OWS type
        """
        permissions = {}

        # get GetProjectSettings
        response = requests.get(
            urljoin(self.qgis_server_url, ows_name),
            params={
                'SERVICE': ows_type,
                'VERSION': '1.3.0',
                'REQUEST': 'GetProjectSettings'
            },
            timeout=30
        )

        if response.status_code != requests.codes.ok:
            self.logger.warn(
                "Could not get GetProjectSettings: %s", response.content
            )
            return permissions

        # parse GetProjectSettings XML
        ElementTree.register_namespace('', 'http://www.opengis.net/wms')
        ElementTree.register_namespace('qgs', 'http://www.qgis.org/wms')
        ElementTree.register_namespace('sld', 'http://www.opengis.net/sld')
        ElementTree.register_namespace(
            'xlink', 'http://www.w3.org/1999/xlink'
        )
        root = ElementTree.fromstring(response.content)

        # use default namespace for XML search
        # namespace dict
        ns = {'ns': 'http://www.opengis.net/wms'}
        # namespace prefix
        np = 'ns:'
        if not root.tag.startswith('{http://'):
            # do not use namespace
            ns = {}
            np = ''

        root_layer = root.find('%sCapability/%sLayer' % (np, np), ns)
        if root_layer is None:
            self.logger.warn("No root layer found: %s", response.content)
            return permissions

        permissions = {
            'qgs_project': ows_name,
            # public layers without facade sublayers: [<layers>]
            'public_layers': [],
            # layers with permitted attributes: {<layer>: [<attrs]}
            'layers': {},
            # queryable layers: [<layers>]
            'queryable_layers': [],
            # layer aliases for feature info results:
            #     {<feature info layer>: <layer>}
            'feature_info_aliases': {},
            # lookup for group layers with restricted sublayers
            # sub layers ordered from bottom to top:
            #     {<group>: [<sub layers]}
            'restricted_group_layers': {},
            # temporary lookup for complete group layers
            'group_layers': {},
            # TODO: extract background layers
            'background_layers': [],
            # print templates: [<template name>]
            'print_templates': []
        }

        # collect layers from layer tree
        self.collect_layers(root_layer, permissions, ns, np, ows_name)

        # collect print templates
        for template in root.findall('.//%sComposerTemplate' % np, ns):
            template_name = template.get('name')
            permissions['print_templates'].append(template_name)

        return permissions

    def collect_layers(self, layer, permissions, ns, np, fallback_name=""):
        """Recursively collect layer info for layer subtree from
        GetProjectSettings.

        :param Element layer: GetProjectSettings layer node
        :param obj permissions: partial OGC service permission
        :param obj ns: Namespace dict
        :param str np: Namespace prefix
        """
        layer_name_tag = layer.find('%sName' % np, ns)
        if layer_name_tag is not None:
            layer_name = layer_name_tag.text
        else:
            layer_name = fallback_name

        permissions['public_layers'].append(layer_name)
        if layer.get('queryable') == '1':
            permissions['queryable_layers'].append(layer_name)
            layer_title = layer.find('%sTitle' % np, ns).text
            permissions['feature_info_aliases'][layer_title] = layer_name

        # collect sub layers if group layer
        group_layers = []
        for sub_layer in layer.findall('%sLayer' % np, ns):
            sub_layer_name = sub_layer.find('%sName' % np, ns).text
            group_layers.append(sub_layer_name)

            self.collect_layers(sub_layer, permissions, ns, np)

        if group_layers:
            permissions['group_layers'][layer_name] = group_layers

        # collect attributes if data layer
        attributes = []
        attrs = layer.find('%sAttributes' % np, ns)
        if attrs is not None:
            for attr in attrs.findall('%sAttribute' % np, ns):
                attributes.append(attr.get('alias', attr.get('name')))
            attributes.append('geometry')
            attributes.append('maptip')

        permissions['layers'][layer_name] = attributes

    def filter_map_permissions(self, default_allow,
                               ows_name, permissions, username,
                               group, session):
        """Filter permitted resources from OGC service permissions.

        Return filtered OGC service permissions and map_id.

        :param str ows_name: Map name
        :param obj permissions: OGC service permissions
        :param str username: User name
        :param str group: Group name
        :param Session session: DB session
        """
        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        if default_allow:
            # query map restrictions
            maps_query = self.resource_restrictions_query(
                    'map', username, group, session
                ).filter(Resource.name == ows_name)

            if maps_query.count() > 0:
                # map not permitted
                return {}, None
        else:  # default_allow == False
            maps_query = self.resource_permission_query(
                    'map', username, group, session
                ).filter(Resource.name == ows_name)

            if maps_query.count() == 0:
                # map not permitted
                return {}, None

        # get map_id
        map_id = None
        maps_query = self.resource_permission_query(
                'map', username, group, session
            ).filter(Resource.name == ows_name)
        map_permission = maps_query.first()
        if map_permission is not None:
            map_id = map_permission.id

        return permissions, map_id

    def filter_layer_permissions(self, default_allow,
                                 map_id, permissions, username,
                                 group, session):
        Resource = self.config_models.model('resources')

        if default_allow:
            # query layer restrictions
            layers_query = self.resource_restrictions_query(
                    'layer', username, group, session
                ).filter(Resource.parent_id == map_id)

            # remove restricted layers
            for layer in layers_query.all():
                self.filter_restricted_layer(layer.name, permissions)
        else:  # default_allow == False
            layers_query = self.resource_permission_query(
                    'layer', username, group, session
                ).filter(Resource.parent_id == map_id)

            # filter permitted layers
            self.filter_permitted_layers(layers_query.all(), permissions)

        return permissions

    def filter_field_permissions(self,
                                 map_id, permissions, username,
                                 group, session):
        # Attributes are always default_allow == True
        Resource = self.config_models.model('resources')

        # query attribute restrictions
        layer_alias = aliased(Resource)
        attrs_query = self.resource_restrictions_query(
                'attribute', username, group, session
            )
        # join to layer resources
        attrs_query = attrs_query.join(
                layer_alias, layer_alias.id == Resource.parent_id
            )
        # filter by map
        attrs_query = attrs_query.filter(layer_alias.parent_id == map_id)
        # include layer name
        attrs_query = attrs_query.with_entities(
                Resource.id, Resource.name, Resource.parent_id,
                layer_alias.name.label('layer_name')
            )

        # group restricted attributes by layer
        layers_attributes = {}
        for attr in attrs_query.all():
            if attr.layer_name not in layers_attributes:
                layers_attributes[attr.layer_name] = []
            layers_attributes[attr.layer_name].append(attr.name)

        for layer in layers_attributes:
            # remove restricted attributes from permitted layers
            if layer in permissions['layers']:
                layer_attrs = permissions['layers'][layer]
                for attr in layers_attributes[layer]:
                    if attr in layer_attrs:
                        layer_attrs.remove(attr)

        return permissions

    def filter_print_template_permissions(
            self, default_allow, map_id, permissions, username, group,
            session):
        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        if default_allow:
            # query print template restrictions
            templates_query = self.resource_restrictions_query(
                    'print_template', username, group, session
                ).filter(Resource.parent_id == map_id)

            # remove restricted print templates
            for template in templates_query.all():
                if template.name in permissions['print_templates']:
                    permissions['print_templates'].remove(template.name)

        else:  # default_allow == False
            templates_query = self.resource_permission_query(
                    'print_template', username, group, session
                ).filter(Resource.parent_id == map_id)
            permissions['print_templates'] = list(
                set(permissions['print_templates']).intersection(
                    templates_query.all()))

        return permissions

    def filter_restricted_layer(self, restricted_layer, permissions):
        """Recursively remove restricted layers.

        :param str restricted_layer: Restricted layer name
        :param obj permissions: OGC service permissions
        """
        # remove restricted layer
        permissions['layers'].pop(restricted_layer, None)
        if restricted_layer in permissions['queryable_layers']:
            permissions['queryable_layers'].remove(restricted_layer)
        if restricted_layer in permissions['public_layers']:
            permissions['public_layers'].remove(restricted_layer)

        # remove restricted layer from feature_info_aliases
        feature_info_alias = None
        for alias in permissions['feature_info_aliases']:
            if permissions['feature_info_aliases'][alias] == restricted_layer:
                feature_info_alias = alias
                break
        if feature_info_alias is not None:
            permissions['feature_info_aliases'].pop(feature_info_alias)

        # update restricted_group_layers
        restricted_group_layers = permissions['restricted_group_layers']
        for group_layer in permissions['group_layers']:
            # find restricted layer in group_layers
            sub_layers = permissions['group_layers'][group_layer]
            if restricted_layer in sub_layers:
                if group_layer not in restricted_group_layers:
                    # add restricted group if not present
                    restricted_group_layers[group_layer] = sub_layers.copy()

                # remove restricted layer
                restricted_group_layers[group_layer].remove(restricted_layer)
                if not restricted_group_layers[group_layer]:
                    # remove empty restricted group
                    restricted_group_layers.pop(group_layer, None)

                    # remove empty group layer
                    self.filter_restricted_layer(
                        group_layer, permissions
                    )

                break

    def filter_permitted_layers(self, permitted_layers, permissions):
        """Recursively remove restricted layers.

        :param str permitted_layers: Permitted layers
        :param obj permissions: OGC service permissions
        """
        layer_names = list(map(lambda l: l.name, permitted_layers))
        permissions['public_layers'] = list(
            set(permissions['public_layers']).intersection(layer_names))
        permissions['queryable_layers'] = list(
            set(permissions['queryable_layers']).intersection(layer_names))
        permissions['layers'] = {
            l: permissions['layers'][l] for l in layer_names
        }

        # filter feature_info_aliases
        permissions['feature_info_aliases'] = {
            k: v for k, v in permissions['feature_info_aliases'].items()
            if v in layer_names
        }

        # update restricted_group_layers
        permissions['restricted_group_layers'] = {}  # TODO
