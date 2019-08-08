import os
from flask import json
from werkzeug.urls import url_parse

from permission_query import PermissionQuery
from themes_config import genThemes


class QWC2ViewerPermission(PermissionQuery):
    '''QWC2ViewerPermission class

    Query permissions for a QWC Map viewer application.
    '''

    # lookup for edit geometry types:
    #     PostGIS geometry type -> QWC2 edit geometry type
    EDIT_GEOM_TYPES = {
        'POINT': 'Point',
        'MULTIPOINT': 'MultiPoint',
        'LINESTRING': 'LineString',
        'MULTILINESTRING': 'MultiLineString',
        'POLYGON': 'Polygon',
        'MULTIPOLYGON': 'MultiPolygon'
    }

    # lookup for edit field types:
    #     PostgreSQL data_type -> QWC2 edit field type
    EDIT_FIELD_TYPES = {
        'bigint': 'number',
        'boolean': 'boolean',
        'character varying': 'text',
        'date': 'date',
        'double precision': 'text',
        'integer': 'number',
        'numeric': 'number',
        'real': 'text',
        'smallint': 'number',
        'text': 'text',
        'time': 'time',
        'timestamp with time zone': 'date',
        'timestamp without time zone': 'date',
        'uuid': 'text'
    }

    def __init__(self, ogc_permission_handler, data_permission_handler,
                 default_allow, config_models, logger):
        """Constructor

        :param ogc_permission_handler: Permission handler for OGC service
        :param data_permission_handler: Permission handler for Data service
        :param bool default_allow: Whether resources are allowed by default
        :param ConfigModels config_models: Helper for ORM models
        :param Logger logger: Application logger
        """
        super(QWC2ViewerPermission, self).__init__(config_models, logger)

        self.ogc_permission_handler = ogc_permission_handler
        self.data_permission_handler = data_permission_handler
        self.default_allow = default_allow

        # get path to QWC2 themes config from ENV
        qwc2_path = os.environ.get('QWC2_PATH', 'qwc2/')
        self.themes_config_path = os.environ.get(
            'QWC2_THEMES_CONFIG', os.path.join(qwc2_path, 'themesConfig.json')
        )

        # get internal QGIS server URL from ENV
        qgis_server_url = os.environ.get('QGIS_SERVER_URL',
                                         'http://localhost/wms/').rstrip('/') + '/'
        self.qgis_server_base_path = url_parse(qgis_server_url).path

    def permissions(self, params, username, group, session):
        '''Query permissions for QWC service.

        Return data for QWC themes.json for available and permitted resources.

        :param obj params: Request parameters
        :param str username: User name
        :param str group: Group name
        :param Session session: DB session
        '''
        # get themes from QWC2 themes config
        with open(self.themes_config_path, encoding='utf-8') as fh:
            config = json.load(fh)

        # query WMS permissions for each theme
        permissions = {}
        self.themes_group_permissions(
            config.get('themes', {}), permissions, username, group, session
        )

        result = genThemes(self.themes_config_path, permissions)

        # add viewer permissions
        result['viewers'] = self.viewer_permissions(username, group, session)

        # add viewer task permissions
        result['viewer_tasks'] = self.viewer_task_permissions(
            username, group, session
        )

        return result

    def themes_group_permissions(self, group_config, permissions, username,
                                 group, session):
        """Recursively collect WMS and edit permissions for each theme in a
        group.

        :param obj group_config: Sub config for theme group
        :param obj permissions: Collected WMS and edit permissions
        :param str username: User name
        :param str group: Group name
        :param Session session: DB session
        """
        theme_items = group_config.get('items', [])
        for item in theme_items:
            url = item.get('url')
            if url:
                # get WMS name as relative path to QGIS server base path
                wms_name = url_parse(url).path
                if wms_name.startswith(self.qgis_server_base_path):
                    wms_name = wms_name[len(self.qgis_server_base_path):]

                # query WMS permissions
                ogc_params = {'ows_type': 'WMS', 'ows_name': wms_name}
                permissions[wms_name] = self.ogc_permission_handler.permissions(
                    ogc_params, username, group, session
                )

                if permissions[wms_name]:
                    # query edit permissions
                    edit_config = self.edit_permissions(
                        wms_name, username, group, session
                    )
                    if edit_config:
                        permissions[wms_name]['edit_config'] = edit_config

        groups = group_config.get('groups', [])
        for sub_group in groups:
            # collect sub group permissions
            self.themes_group_permissions(
                sub_group, permissions, username, group, session
            )

    def edit_permissions(self, map_name, username, group, session):
        """Query edit permissions for a theme.

        :param str map_name: Map name (matches WMS and QGIS project)
        :param str username: User name
        :param str group: Group name
        :param Session session: DB session
        """
        edit_config = {}

        edit_datasets = self.edit_datasets(map_name, username, group, session)
        for dataset in edit_datasets:
            edit_layer_config = self.edit_layer_config(
                map_name, dataset, username, group, session
            )
            if edit_layer_config:
                edit_config[dataset] = edit_layer_config

        return edit_config

    def edit_datasets(self, map_name, username, group, session):
        """Get permitted edit datasets for a map.

        :param str map_name: Map name
        :param str username: User name
        :param str group: Group name
        :param Session session: DB session
        """
        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        # query map permissions
        maps_query = self.user_permissions_query(username, group, session). \
            join(Permission.resource).filter(Resource.type == 'map'). \
            filter(Resource.name == map_name). \
            distinct(Resource.name)
        map_id = None
        for map_permission in maps_query.all():
            map_id = map_permission.resource.id

        if map_id is None:
            # map not found or not permitted
            return []

        # query writable data permissions
        edit_datasets = []
        data_resource_types = [
            'data',
            'data_create', 'data_update', 'data_delete'
        ]
        data_query = self.user_permissions_query(username, group, session). \
            join(Permission.resource). \
            filter(Resource.type.in_(data_resource_types)). \
            filter(Resource.parent_id == map_id)
        for data_permission in data_query.all():
            if (
                data_permission.resource.type == 'data'
                and not data_permission.write
            ):
                # skip read-only 'data'
                continue

            # collect distinct datasets
            if data_permission.resource.name not in edit_datasets:
                edit_datasets.append(data_permission.resource.name)

        return edit_datasets

    def edit_layer_config(self, map_name, layer_name, username, group,
                          session):
        """Get permitted edit config for a dataset.

        :param str map_name: Map name
        :param str layer_name: Data layer name
        :param str username: User name
        :param str group: Group name
        :param Session session: DB session
        """
        dataset = "%s.%s" % (map_name, layer_name)

        # query data permissions
        data_params = {'dataset': dataset}
        permissions = self.data_permission_handler.permissions(
            data_params, username, group, session
        )

        if not permissions:
            # data permissions are empty
            self.logger.warn(
                "Could not get data permissions for edit dataset '%s'" %
                dataset
            )
            return {}

        if permissions['geometry_type'] not in self.EDIT_GEOM_TYPES:
            # unsupported geometry type
            table = "%s.%s" % (
                permissions.get('schema'), permissions.get('table_name')
            )
            self.logger.warn(
                "Unsupported geometry type '%s' for edit dataset '%s' "
                "on table '%s'" %
                (permissions['geometry_type'], dataset, table)
            )
            return {}

        # write permission
        writable = permissions.get('writable', False)
        # CRUD permissions
        creatable = permissions.get('creatable', writable)
        readable = permissions.get('readable', True)
        updatable = permissions.get('updatable', writable)
        deletable = permissions.get('deletable', writable)

        # update and delete require readable for selection in viewer
        updatable = updatable and readable
        deletable = deletable and readable

        if not creatable and not readable:
            # dataset can neither be created nor selected
            return {}

        # set attributes to read-only if only deletable
        read_only_attrs = not creatable and not updatable

        fields = []
        for attr in permissions['attributes']:
            field = permissions['fields'].get(attr, {})
            alias = field.get('alias', attr)
            data_type = self.EDIT_FIELD_TYPES.get(
                field.get('data_type'), 'text'
            )

            edit_field = {
                'id': attr,
                'name': alias,
                'type': data_type
            }

            if 'constraints' in field:
                # add any constraints
                edit_field['constraints'] = field['constraints']
                if 'values' in field['constraints']:
                    edit_field['type'] = 'list'

            if read_only_attrs:
                # set read-only constraint
                edit_field['constraints'] = edit_field.get('constraints', {})
                edit_field['constraints']['readOnly'] = True

            fields.append(edit_field)

        geometry_type = self.EDIT_GEOM_TYPES.get(permissions['geometry_type'])

        return {
            'layerName': layer_name,
            'editDataset': dataset,
            'fields': fields,
            'geomType': geometry_type
        }

    def viewer_permissions(self, username, group, session):
        """Get permitted viewers.

        :param str username: User name
        :param str group: Group name
        :param Session session: DB session
        """
        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        # query viewer permissions
        viewers = []
        viewers_query = self.user_permissions_query(
                username, group, session
            ).join(Permission.resource). \
            filter(Resource.type == 'viewer'). \
            distinct(Resource.name)
        for permission in viewers_query.all():
            viewers.append(permission.resource.name)

        return viewers

    def viewer_task_permissions(self, username, group, session):
        """Get permitted viewer tasks.

        :param str username: User name
        :param str group: Group name
        :param Session session: DB session
        """
        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        # query viewer permissions
        viewer_tasks = {}

        # collect permittable viewer tasks
        permittable_tasks_query = session.query(Resource). \
            filter(Resource.type == 'viewer_task'). \
            distinct(Resource.name)
        permittable_tasks = [r.name for r in permittable_tasks_query.all()]

        if self.default_allow:
            # query viewer task restrictions
            viewer_tasks_query = self.resource_restrictions_query(
                'viewer_task', username, group, session
            )
            restricted_tasks = [r.name for r in viewer_tasks_query.all()]

            for task in permittable_tasks:
                viewer_tasks[task] = task not in restricted_tasks
        else:
            # query viewer task permissions
            viewer_tasks_query = self.resource_permission_query(
                'viewer_task', username, group, session
            )
            permitted_tasks = [r.name for r in viewer_tasks_query.all()]

            for task in permittable_tasks:
                viewer_tasks[task] = task in permitted_tasks

        return viewer_tasks
