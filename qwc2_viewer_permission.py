import os
from flask import json
from werkzeug.urls import url_parse

from themes_config import genThemes


class QWC2ViewerPermission():
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

        # get internal QGIS server URL from ENV
        qgis_server_url = os.environ.get('QGIS_SERVER_URL',
                                         'http://localhost:8001/ows/')
        self.qgis_server_base_path = url_parse(qgis_server_url).path

    def permissions(self, params, username):
        '''Query permissions for QWC service.

        Return data for QWC themes.json for available and permitted resources.

        :param obj params: Request parameters
        :param str username: User name
        '''
        # get themes from QWC2 themes config
        qwc2_path = os.environ.get('QWC2_PATH', 'qwc2/')
        themes_config = os.getenv('QWC2_THEMES_CONFIG',
                                  os.path.join(qwc2_path, 'themesConfig.json'))
        with open(themes_config, encoding='utf-8') as fh:
            config = json.load(fh)

        # query WMS permissions for each theme
        permissions = {}
        self.themes_group_permissions(
            config.get('themes', {}), permissions, username
        )

        return genThemes(themes_config, permissions)

    def themes_group_permissions(self, group_config, permissions, username):
        """Recursively collect query WMS permissions for each theme in a group.

        :param obj group_config: Sub config for theme group
        :param obj permissions: Collected WMS permissions
        :param str username: User name
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
                    ogc_params, username
                )

        groups = group_config.get('groups', [])
        for group in groups:
            # collect sub group permissions
            self.themes_group_permissions(group, permissions, username)
