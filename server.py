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
last_update_response = create_model(api, 'LastUpdate', [
    ['permissions_updated_at', fields.String(
        required=True,
        description='Timestamp of last permissions update',
        example='2018-07-09 12:00:00'
    )]
])

cache_project_settings_response = create_model(api, 'CacheProjectSettings', [
    ['cached_settings', fields.Raw(
        required=True,
        description='List of service names for which settings were cached',
        example=['name1', 'name2']
    )]
])

resource_permissions_response = create_model(api, 'Resource permissions', [
    ['resource_type', fields.String(required=True, description='Resource type',
                                    example='map')],
    ['permissions', fields.Raw(required=True,
                               description='Permitted resources',
                               example={'1': {'id': 1, 'name': 'qwc_demo',
                                        'parent_id': None, 'writable': False}}
                               )]
])

resource_restrictions_response = create_model(api, 'Resource restrictions', [
    ['resource_type', fields.String(required=True, description='Resource type',
                                    example='data')],
    ['restrictions', fields.Raw(required=True,
                                description='Restricted resources',
                                example={'2': {'id': 2, 'name': 'edit_points',
                                         'parent_id': 1}}
                                )]
])

service_permissions_response = create_model(api, 'Service permissions', [
    ['service', fields.String(required=True, description='Service type',
                              example='ogc')],
    ['permissions', fields.Raw(required=True,
                               description='Service specific permissions',
                               example={'layers': '...'})]
])


# routes
@api.route('/last_update')
class LastUpdate(Resource):
    @api.doc('last_update')
    @api.marshal_with(last_update_response)
    def get(self):
        """Get timestamp of last permissions update"""
        return config_service.last_update()

@api.route('/cache_project_settings')
class CacheProjectSettings(Resource):
    @api.doc('cache_project_settings')
    @api.marshal_with(cache_project_settings_response)
    def get(self):
        """Cache all known project settings"""
        return config_service.cache_project_settings()

@api.route('/permissions/<resource_type>')
@api.param('resource_type', 'Resource type (e.g. <i>map</i>, <i>layer</i>)',
           default='map')
@api.param('username', 'User name')
@api.param('group', 'Group name')
@api.param('name', 'Resource name filter (optional)')
@api.param('parent_id', 'Parent resource ID filter (optional)')
class Permissions(Resource):
    @api.doc('resource_permissions')
    @api.marshal_with(resource_permissions_response)
    def get(self, resource_type):
        """Query permitted resources for a resource type

        <b>permissions</b> are empty if resource type is not available or \
        not permitted
        """
        username = request.args.get('username', None)
        group = request.args.get('group', None)
        result = config_service.resource_permissions(
            resource_type, request.args, username, group
        )
        if 'error' not in result:
            return {
                'resource_type': resource_type,
                'permissions': result['permissions']
            }
        else:
            api.abort(404, result['error'])


@api.route('/restrictions/<resource_type>')
@api.param('resource_type', 'Resource type (e.g. <i>map</i>, <i>layer</i>)',
           default='map')
@api.param('username', 'User name')
@api.param('group', 'Group name')
@api.param('name', 'Resource name filter (optional)')
@api.param('parent_id', 'Parent resource ID filter (optional)')
class Restrictions(Resource):
    @api.doc('resource_restrictions')
    @api.marshal_with(resource_restrictions_response)
    def get(self, resource_type):
        """Query restricted resources for a resource type

        <b>permissions</b> are empty if resource type is not available or \
        not restricted
        """
        username = request.args.get('username', None)
        group = request.args.get('group', None)
        result = config_service.resource_restrictions(
            resource_type, request.args, username, group
        )
        if 'error' not in result:
            return {
                'resource_type': resource_type,
                'restrictions': result['restrictions']
            }
        else:
            api.abort(404, result['error'])


@api.route('/<service>')
@api.response(404, 'Service type not found')
@api.param('service', 'Service type (<i>ogc</i>, <i>data</i>, <i>qwc</i>)',
           default='ogc')
@api.param('username', 'User name')
@api.param('group', 'Group name')
@api.param('ows_name', 'WMS/WFS name', default='qwc_demo')
@api.param('ows_type', 'OWS type (<i>WMS</i> or <i>WFS</i>)', default='WMS')
@api.param('dataset', 'Dataset ID', default='qwc_demo.edit_points')
class ServicePermissions(Resource):
    @api.doc('service_permissions')
    @api.marshal_with(service_permissions_response)
    def get(self, service):
        """Query permissions for a service

        <b>permissions</b> are empty if service is not available or \
        not permitted

        Additional query parameters are service specific:

        * <b>ows_name</b>: OGC and FeatureInfo services
        * <b>ows_type</b>: OGC service
        * <b>dataset</b>: Data service
        """
        username = request.args.get('username', None)
        group = request.args.get('group', None)
        result = config_service.service_permissions(
            service, request.args, username, group
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
    from flask_cors import CORS
    CORS(app)
    app.run(host='localhost', port=5010, debug=True)
