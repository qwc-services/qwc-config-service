import os
from flask import json
from werkzeug.urls import url_parse

from permission_query import PermissionQuery
from themes_config import genThemes


class QWC2ViewerPermission(PermissionQuery):
    '''QWC2ViewerPermission class

    Query permissions for a QWC service.
    '''

    def __init__(self, ogc_permission_handler, logger):
        """Constructor

        :param ogc_permission_handler: Permission handler for WMS requests
        :param Logger logger: Application logger
        """
        self.ogc_permission_handler = ogc_permission_handler
        self.logger = logger

        # get path to QWC2 themes config from ENV
        qwc2_path = os.environ.get('QWC2_PATH', 'qwc2/')
        self.themes_config_path = os.environ.get(
            'QWC2_THEMES_CONFIG', os.path.join(qwc2_path, 'themesConfig.json')
        )

        # get internal QGIS server URL from ENV
        qgis_server_url = os.environ.get('QGIS_SERVER_URL',
                                         'http://localhost:8001/ows/')
        self.qgis_server_base_path = url_parse(qgis_server_url).path

    def permissions(self, params, username, session):
        '''Query permissions for QWC service.

        Return data for QWC themes.json for available and permitted resources.

        :param obj params: Request parameters
        :param str username: User name
        :param Session session: DB session
        '''
        # get themes from QWC2 themes config
        with open(self.themes_config_path, encoding='utf-8') as fh:
            config = json.load(fh)

        # query WMS permissions for each theme
        permissions = {}
        self.themes_group_permissions(
            config.get('themes', {}), permissions, username, session
        )

        return genThemes(self.themes_config_path, permissions)

    def themes_group_permissions(self, group_config, permissions, username,
                                 session):
        """Recursively collect query WMS permissions for each theme in a group.

        :param obj group_config: Sub config for theme group
        :param obj permissions: Collected WMS permissions
        :param str username: User name
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
                    ogc_params, username, session
                )

        groups = group_config.get('groups', [])
        for group in groups:
            # collect sub group permissions
            self.themes_group_permissions(group, permissions, username)
