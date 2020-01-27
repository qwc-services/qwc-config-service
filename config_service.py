from datetime import datetime
import os

from qwc_config_db.config_models import ConfigModels
from qwc_services_core.database import DatabaseEngine
from data_service_permission import DataServicePermission
from ogc_service_permission import OGCServicePermission
from qwc2_viewer_permission import QWC2ViewerPermission
from resource_permission import ResourcePermission


class ConfigService:
    """ConfigService class

    Query service specific permissions.
    """

    def __init__(self, logger):
        """Constructor

        :param Logger logger: Application logger
        """
        self.logger = logger
        self.db_engine = DatabaseEngine()
        self.config_models = ConfigModels(self.db_engine)
        default_allow = os.environ.get(
            'DEFAULT_ALLOW', 'True') == 'True'
        data_permission_handler = DataServicePermission(
            self.db_engine, self.config_models, logger
        )
        self.project_settings_cache = {}
        ogc_permission_handler = OGCServicePermission(
            default_allow, self.config_models, logger, self.project_settings_cache
        )
        qwc_permission_handler = QWC2ViewerPermission(
            ogc_permission_handler, data_permission_handler,
            default_allow, self.config_models, logger,
            self.project_settings_cache
        )
        self.permission_handlers = {
            'data': data_permission_handler,
            'ogc': ogc_permission_handler,
            'qwc': qwc_permission_handler
        }

        self.resource_permission_handler = ResourcePermission(
            self.config_models, logger
        )

        # get path to QWC2 themes config from ENV
        qwc2_path = os.environ.get('QWC2_PATH', 'qwc2/')
        self.themes_config_path = os.environ.get(
            'QWC2_THEMES_CONFIG', os.path.join(qwc2_path, 'themesConfig.json')
        )

        if os.environ.get("__QWC_CONFIG_SERVICE_PROJECT_SETTINGS_STARTUP_CACHE", "0") == "1":
            self.cache_project_settings()

    def last_update(self):
        """Return UTC timestamp of last permissions update."""
        # get modification time of QWC2 themes config file
        config_updated_at = None
        if os.path.isfile(self.themes_config_path):
            config_updated_at = datetime.utcfromtimestamp(
                os.path.getmtime(self.themes_config_path)
            )

        # create session for ConfigDB
        session = self.config_models.session()

        # query timestamp
        LastUpdate = self.config_models.model('last_update')
        query = session.query(LastUpdate.updated_at)
        last_update = query.first()
        if last_update is not None:
            if config_updated_at is not None:
                # use latest of both timestamps
                updated_at = max(last_update.updated_at, config_updated_at)
            else:
                # use timestamp from ConfigDB
                updated_at = last_update.updated_at
        else:
            # no entry in ConfigDB, use config timestamp or now
            updated_at = config_updated_at or datetime.utcnow()

        # close session
        session.close()

        return {
            'permissions_updated_at': updated_at.strftime("%Y-%m-%d %H:%M:%S")
        }

    def service_permissions(self, service, params, username, group):
        """Return permissions for a service and a dataset.

        :param str service: Service type
        :param obj params: Service specific request parameters
        :param str username: User name
        :param str group: Group name
        """
        permission_handler = self.permission_handlers.get(service, None)
        if permission_handler is not None:
            # create session for ConfigDB
            session = self.config_models.session()

            # query permissions
            permissions = permission_handler.permissions(
                params, username, group, session
            )

            # close session
            session.close()

            return {
                'permissions': permissions
            }
        else:
            return {'error': "Service type '%s' not found" % service}

    def resource_permissions(self, resource_type, params, username, group):
        """Return permitted resources for a resource type.

        :param str resource_type: Resource type
        :param obj params: Request parameters
        :param str username: User name
        :param str group: Group name
        """
        # create session for ConfigDB
        session = self.config_models.session()

        # query permitted resources
        permissions = self.resource_permission_handler.permissions(
            resource_type, params, username, group, session
        )

        # close session
        session.close()

        return {
            'permissions': permissions
        }

    def resource_restrictions(self, resource_type, params, username, group):
        """Return restricted resources for a resource type.

        :param str resource_type: Resource type
        :param obj params: Request parameters
        :param str username: User name
        :param str group: Group name
        """
        # create session for ConfigDB
        session = self.config_models.session()

        # query restricted resources
        restrictions = self.resource_permission_handler.restrictions(
            resource_type, params, username, group, session
        )

        # close session
        session.close()

        return {
            'restrictions': restrictions
        }

    def cache_project_settings(self):
        return self.permission_handlers["ogc"].cache_project_settings()
