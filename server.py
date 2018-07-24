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

last_update_response = create_model(api, 'LastUpdate', [
    ['permissions_updated_at', fields.String(
        required=True,
        description='Timestamp of last permissions update',
        example='2018-07-09 12:00:00'
    )]
])


# routes
@api.route('/last_update')
class LastUpdate(Resource):
    @api.doc('last_update')
    @api.marshal_with(last_update_response)
    def get(self):
        """Get timestamp of last permissions update"""
        return config_service.last_update()


@api.route('/<service>')
@api.response(404, 'Service type not found')
@api.param('service', 'Service type (<i>ogc</i>, <i>data</i>, <i>qwc</i>)',
           default='ogc')
@api.param('username', 'User name')
@api.param('ows_name', 'WMS/WFS name', default='qwc_demo')
@api.param('ows_type', 'OWS type (<i>WMS</i> or <i>WFS</i>)', default='WMS')
@api.param('dataset', 'Dataset ID', default='qwc_demo.edit_points')
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
        * <b>dataset</b>: Data service
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
