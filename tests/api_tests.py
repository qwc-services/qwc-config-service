import unittest

from flask import Response, json
from flask.testing import FlaskClient

import server


class ApiTestCase(unittest.TestCase):
    """Test case for server API"""

    def setUp(self):
        server.app.testing = True
        self.app = FlaskClient(server.app, Response)

    def get(self, url):
        """Send GET request and return status code and decoded JSON from
        response.
        """
        response = self.app.get(url)
        return response.status_code, json.loads(response.data)

    def check_base_permission(self, service, dataset, json_data):
        self.assertEqual(service, json_data['service'])
        self.assertIn('permissions', json_data)
        self.assertIsInstance(json_data['permissions'], dict,
                              "Permissions are not a dict")

    # data service permissions

    def check_data_permission(self, dataset, json_data):
        self.check_base_permission('data', dataset, json_data)

    def test_data_service_permission(self):
        status_code, json_data = self.get(
            '/data?dataset=qwc_demo.edit_points'
        )
        self.assertEqual(200, status_code, "Status code is not OK")
        self.check_data_permission('places', json_data)
        permissions = json_data['permissions']
        self.assertIsInstance(permissions['dataset'], str,
                              "dataset is not an string")
        self.assertEqual(['id', 'name', 'description', 'num', 'value', 'type',
                         'amount', 'validated', 'datetime'],
                         permissions['attributes'])

        self.assertIsInstance(permissions['writable'], bool,
                              "writable is not an boolean")
        self.assertIsInstance(permissions['schema'], str,
                              "schema is not an string")
        self.assertIsInstance(permissions['table_name'], str,
                              "table_name is not an string")
        self.assertIsInstance(permissions['primary_key'], str,
                              "primary_key is not an string")
        self.assertIsInstance(permissions['geometry_column'], str,
                              "geometry_column is not an string")
        self.assertIsInstance(permissions['geometry_type'], str,
                              "geometry_type is not an string")
        self.assertIsInstance(permissions['srid'], int,
                              "srid is not an integer")

    def test_data_service_permission_invalid_dataset(self):
        status_code, json_data = self.get('/data?dataset=test')
        self.assertEqual(200, status_code, "Status code is not OK")
        self.check_data_permission('test', json_data)
        permissions = json_data['permissions']
        self.assertEqual({}, permissions, "Permissions are not empty")

    def test_qwc_service_permissions(self):
        status_code, json_data = self.get('/qwc')
        self.assertEqual(200, status_code, "Status code is not OK")
        self.assertIn('permissions', json_data)
        self.assertIsInstance(json_data['permissions'], dict,
                              "Permissions are not a dict")

    def check_layer_field_permission(self, layers_permissions):
        self.assertIn('edit_points', layers_permissions.keys())
        self.assertIn('name', layers_permissions['edit_points'])

    def test_ogc_service_permissions(self):
        status_code, json_data = self.get(
            '/ogc?ows_type=WMS&ows_name=qwc_demo')
        self.assertEqual(200, status_code, "Status code is not OK")
        self.assertIn('permissions', json_data)
        self.assertIsInstance(json_data['permissions'], dict,
                              "Permissions are not a dict")
        permissions = json_data['permissions']
        self.assertEqual(permissions['qgs_project'], 'qwc_demo')
        self.assertEqual(['qwc_demo', 'edit_demo', 'edit_points', 'edit_lines',
                          'edit_polygons', 'geographic_lines', 'country_names',
                          'states_provinces', 'countries', 'osm_bg',
                          'bluemarble_bg'],
                         permissions['public_layers'])
        self.check_layer_field_permission(permissions['layers'])
        self.assertEqual(permissions['print_templates'], ['A4 Landscape'])
