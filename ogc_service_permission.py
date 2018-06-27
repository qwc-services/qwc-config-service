import os
from urllib.parse import urljoin
from xml.etree import ElementTree

from flask import json
import requests


class OGCServicePermission():
    """OGCServicePermission class

    Query permissions for an OGC service.
    """

    def __init__(self, logger):
        """Constructor

        :param Logger logger: Application logger
        """
        self.logger = logger

        # get internal QGIS server URL from ENV
        # (default: local qgis-server container)
        self.qgis_server_url = os.environ.get('QGIS_SERVER_URL',
                                              'http://localhost:8001/ows/')

    def permissions(self, params, username):
        """Query permissions for OGC service.

        Return OGC service permissions if available and permitted.

        :param obj params: Request parameters with
                           ows_name=<OWS service name>&ows_type=<OWS type>
        :param str username: User name
        """
        permissions = {}

        ows_name = params.get('ows_name')
        ows_type = params.get('ows_type')

        if ows_type not in ['WMS', 'WFS']:
            # unsupported OWS type
            return permissions

        # get complete OGC service permissions from GetProjectSettings
        permissions = self.parseProjectSettings(ows_name, ows_type)

        # TODO: filter restricted resources

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
            'background_layers': []
        }

        # collect layers from layer tree
        self.collect_layers(root_layer, permissions, ns, np)

        return permissions

    def collect_layers(self, layer, permissions, ns, np):
        """Recursively collect layer info for layer subtree from
        GetProjectSettings.

        :param Element layer: GetProjectSettings layer node
        :param obj permissions: partial OGC service permission
        :param obj ns: Namespace dict
        :param str np: Namespace prefix
        """
        layer_name = layer.find('%sName' % np, ns).text

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

        permissions['layers'][layer_name] = attributes
