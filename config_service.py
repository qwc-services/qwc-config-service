from qwc_services_core.database import DatabaseEngine
from qwc_config_db.config_models import ConfigModels
from ogc_service_permission import OGCServicePermission
from qwc2_viewer_permission import QWC2ViewerPermission


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
        ogc_permission_handler = OGCServicePermission(
            self.config_models, logger
        )
        self.permission_handlers = {
            'ogc': ogc_permission_handler,
            'qwc': QWC2ViewerPermission(ogc_permission_handler, logger)
        }

    def service_permissions(self, service, params, username):
        """Return permissions for a service and a dataset.

        :param str service: Service type
        :param obj params: Service specific request parameters
        :param str username: User name
        """
        permission_handler = self.permission_handlers.get(service, None)
        if permission_handler is not None:
            # create session for ConfigDB
            session = self.config_models.session()

            # query permissions
            permissions = permission_handler.permissions(
                params, username, session
            )

            # close session
            session.close()

            return {
                'permissions': permissions
            }
        else:
            return {'error': "Service type '%s' not found" % service}
