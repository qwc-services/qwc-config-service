from flask import json

from permission_query import PermissionQuery
from qgs_reader import QGSReader


class DataServicePermission(PermissionQuery):
    """DataServicePermission class

    Query permissions for a data service.
    """

    def permissions(self, params, username, session):
        """Query permissions for editing a dataset.

        Return dataset edit permissions if available and permitted.

        Dataset ID can be either '<QGS name>.<Data layer name>' for a specific
        QGIS project or '<Data layer name>' if the data layer name is unique.

        :param obj params: Request parameters with dataset='<Dataset ID>'
        :param str username: User name
        :param Session session: DB session
        """
        permissions = {}

        dataset = params.get('dataset', '')
        parts = dataset.split('.')
        if len(parts) > 1:
            map_name = parts[0]
            layer_name = parts[1]
        else:
            # no map name given
            map_name = None
            layer_name = dataset

        data_permissions = self.data_permissions(
            map_name, layer_name, username, session
        )

        if data_permissions['permitted']:
            # get layer metadata from QGIS project
            qgs_reader = QGSReader(self.logger)
            if qgs_reader.read(data_permissions['map_name']):
                permissions = qgs_reader.layer_metadata(layer_name)

            if permissions:
                permissions.update({
                    'dataset': dataset,
                    'writable': data_permissions['writable']
                })

                self.filter_restricted_attributes(
                    data_permissions['restricted_attributes'],
                    permissions
                )

        return permissions

    def data_permissions(self, map_name, layer_name, username, session):
        """Query resource permissions and return whether map and data layer are
        permitted and writable, and any restricted attributes.

        If map_name is None, the data permission with highest priority is used.

        :param str map_name: Map name
        :param str layer_name: Data layer name
        :param str username: User name
        :param Session session: DB session
        """
        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        map_id = None
        if map_name is None:
            # find map for data layer name
            data_query = self.user_permissions_query(username, session). \
                join(Permission.resource).filter(Resource.type == 'data'). \
                filter(Resource.name == layer_name). \
                order_by(Permission.priority.desc()). \
                distinct(Permission.priority)
            # use data permission with highest priority
            data_permission = data_query.first()
            if data_permission is not None:
                map_id = data_permission.resource.parent_id
                map_query = session.query(Resource). \
                    filter(Resource.type == 'map'). \
                    filter(Resource.id == map_id)
                map_obj = map_query.first()
                if map_obj is not None:
                    map_name = map_obj.name
                    self.logger.info(
                        "No map name given, using map '%s'" % map_name
                    )
        else:
            # query map permissions
            maps_query = self.user_permissions_query(username, session). \
                join(Permission.resource).filter(Resource.type == 'map'). \
                filter(Resource.name == map_name)
            for map_permission in maps_query.all():
                map_id = map_permission.resource.id

        if map_id is None:
            # map not found or not permitted
            # NOTE: map without resource record cannot have data layers
            return {
                'permitted': False
            }

        # query data permissions
        permitted = False
        writable = False
        restricted_attributes = []
        data_query = self.user_permissions_query(username, session). \
            join(Permission.resource).filter(Resource.type == 'data'). \
            filter(Resource.parent_id == map_id). \
            filter(Resource.name == layer_name). \
            order_by(Permission.priority.desc()). \
            distinct(Permission.priority)
        # use data permission with highest priority
        data_permission = data_query.first()
        if data_permission is not None:
            permitted = True
            writable = data_permission.write

            # query attribute restrictions
            attrs_query = self.resource_restrictions_query(
                'attribute', username, session
            ).filter(Resource.parent_id == data_permission.resource_id)
            for attr in attrs_query.all():
                restricted_attributes.append(attr.name)

        return {
            'map_name': map_name,
            'permitted': permitted,
            'writable': writable,
            'restricted_attributes': restricted_attributes
        }

    def filter_restricted_attributes(self, restricted_attributes, permissions):
        """Filter restricted attributes from Data service permissions.

        :param list[str] restricted_attributes: List of restricted attributes
        :param obj permissions: Data service permissions
        """
        for attr in restricted_attributes:
            if attr in permissions['attributes']:
                permissions['attributes'].remove(attr)
