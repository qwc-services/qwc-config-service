import os
import sys

from flask import Flask, request
from flask_restplus import Api, Resource, fields

from qwc_services_core.api import create_model
from config_service import ConfigService


# Flask application
app = Flask(__name__)
api = Api(app, version='1.0', title='Config service API',
          description='API for QWC Config service',
          default_label='Config query operations', doc='/api/'
          )
# disable verbose 404 error message
app.config['ERROR_404_HELP'] = False

# create config service
config_service = ConfigService(app.logger)


# Api models
permissions_response = create_model(api, 'Permissions', [
    ['service', fields.String(required=True, description='Service type',
                              example='ogc')],
    ['permissions', fields.Raw(required=True,
                               description='Service specific permissions',
                               example={'layers': '...'})]
])


# routes
@api.route('/<service>')
@api.response(404, 'Service type not found')
@api.param('service', 'Service type', default='ogc')
@api.param('username', 'User name')
@api.param('ows_name', 'WMS/WFS name', default='qwc_demo')
@api.param('ows_type', 'OWS type (WMS or WFS', default='WMS')
class ServicePermissions(Resource):
    @api.doc('permissions')
    @api.marshal_with(permissions_response)
    def get(self, service):
        """Query permissions for a service

        <b>permissions</b> are empty if service is not available or
        not permitted

        Additional query parameters are service specific:

        * <b>ows_name</b>: OGC and FeatureInfo services
        * <b>ows_type</b>: OGC service
        """
        username = request.args.get('username', None)
        result = config_service.service_permissions(
            service, request.args, username
        )
        if 'error' not in result:
            return {
                'service': service,
                'permissions': result['permissions']
            }
        else:
            api.abort(404, result['error'])


# local webserver
if __name__ == '__main__':
    print("Starting Config service...")
    app.run(host='localhost', port=5010, debug=True)
