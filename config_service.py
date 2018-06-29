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

        ogc_permission_handler = OGCServicePermission(logger)
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
            # query permissions
            permissions = permission_handler.permissions(
                params, username
            )

            return {
                'permissions': permissions
            }
        else:
            return {'error': "Service type '%s' not found" % service}
