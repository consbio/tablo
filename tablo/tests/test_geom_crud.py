import datetime
import json
import random
import string

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.utils.timezone import datetime

from tastypie.models import ApiKey

from tablo.models import FeatureService, FeatureServiceLayer
from tablo.utils import json_date_serializer

API_KEY = 'secretkey'
USERNAME = 'admin'
PASSWORD = '123456'

# API Urls
API_URL_READ = '/tablo/arcgis/rest/services/{feature_id}/FeatureServer/0/query/'
API_URL_EDIT = '/api/v1/featureservice/{feature_id}/apply-edits/'

"""Datasets props
{
    'prop1': integer,
    'prop2': integer,
    'db_creator': text,
    'db_created_data': date,
}
Each dataset is prepopulated with 10 random entries, i.e. random props and random geometries, with ids from 1 to 10.
"""

TYPE_RANDOMIZER = {
    'int': lambda: random.randint(-1000, 10000),
    'str': lambda: ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(random.randint(1, 255))),
    'date': lambda: datetime.now().isoformat()
}


class TestCRUD(TestCase):
    def setUp(self):
        super(TestCRUD, self).setUp()

        with open('tablo/tests/tables.sql', 'r') as sql:
            with connection.cursor() as cur:
                cur.execute(sql.read())

        user = User.objects.create_user(**{'username': USERNAME, 'password': PASSWORD})
        ApiKey.objects.create(**{'user': user, 'key': API_KEY})

        self.feature_service_point = FeatureService.objects.create(**{
            'spatial_reference': json.dumps({'wkid': 3857}),
            'description': 'FeatureServicePointTest'
        })

        self.feature_service_layer_point = FeatureServiceLayer.objects.create(
            service=self.feature_service_point,
            layer_order=0,
            table='db_point_test',  # created using tables.sql
            name='FeatureServiceLayerPointTest',
            object_id_field='db_id',
            geometry_type='esriGeometryPoint'
        )

        self.feature_service_polyline = FeatureService.objects.create(**{
            'spatial_reference': json.dumps({'wkid': 3857}),
            'description': 'FeatureServicePolylineTest'
        })

        self.feature_service_layer_polyline = FeatureServiceLayer.objects.create(
            service=self.feature_service_polyline,
            layer_order=0,
            table='db_polyline_test',  # created using tables.sql
            name='FeatureServiceLayerPolylineTest',
            object_id_field='db_id',
            geometry_type='esriGeometryPolyline'
        )

        self.feature_service_polygon = FeatureService.objects.create(**{
            'spatial_reference': json.dumps({'wkid': 3857}),
            'description': 'FeatureServicePolygonTest'
        })

        self.feature_service_layer_polygon = FeatureServiceLayer.objects.create(
            service=self.feature_service_polygon,
            layer_order=0,
            table='db_polygon_test',  # created using tables.sql
            name='FeatureServiceLayerPolygonTest',
            object_id_field='db_id',
            geometry_type='esriGeometryPolygon'
        )

    def get_api_key(self):
        return 'ApiKey {user}:{api_key}'.format(user=USERNAME, api_key=API_KEY)

    def dataset_modifier(self, geom_type, data):
        resp = self.client.post(
            API_URL_EDIT.format(feature_id=getattr(self, 'feature_service_{}'.format(geom_type)).id),
            data=data,
            HTTP_AUTHORIZATION=self.get_api_key()
        )
        return json.loads(resp.content.decode('utf8'))

    def generate_random_point(self):
        return {
            'x': random.uniform(-1, 1) * 180,
            'y': random.uniform(-1, 1) * 90,
            'spatialReference': {'wkid': 4326}
        }

    def generate_random_polyline(self):
        num_of_lines = random.randint(1, 10)
        num_of_point = random.randint(2, 10)    # minimum of 2 points are needed for a line
        paths = []
        for i in range(num_of_lines):
            path = []
            for j in range(num_of_point):
                p = self.generate_random_point()
                path.append([p['x'], p['y']])
            paths.append(path)
        return {
            'paths': paths,
            'spatialReference': {'wkid': 4326}
        }

    def generate_random_polygon(self):
        num_of_polygons = random.randint(1, 10)
        num_of_point = random.randint(3, 10)    # minimum of 3 points are needed for a polygon
        rings = []
        for i in range(num_of_polygons):
            ring = []
            for j in range(num_of_point):
                p = self.generate_random_point()
                ring.append([p['x'], p['y']])
            ring.append(ring[0])
            rings.append(ring)

        return {
            'rings': rings,
            'spatialReference': {'wkid': 4326}
        }

    def generate_random_data(self, fields={}, n=1, geom_type=None, is_new_entry=False):
        data = []
        if is_new_entry:
            fields.update({'db_creator': 'str', 'db_created_date': 'date'})

        for i in range(n):
            entry = {'attributes': {}}
            for f, t in fields.items():
                entry['attributes'][f] = TYPE_RANDOMIZER[t]() if callable(TYPE_RANDOMIZER.get(t)) else t
            if geom_type:
                entry['geometry'] = getattr(self, 'generate_random_{}'.format(geom_type))()
            data.append(entry)
        return data

    # Point and some general tests
    def test_read_points(self):
        # makes sure data returned from api matches the entries in db_point_test
        resp = self.client.get(API_URL_READ.format(feature_id=self.feature_service_point.id))
        with connection.cursor() as cur:
            for point in resp.json()['features']:
                cur.execute('SELECT * FROM db_point_test WHERE db_id = %s', (point['attributes']['db_id'],))
                column_names = [desc[0] for desc in cur.description]
                db_point = dict(zip(column_names, cur.fetchall()[0]))
                self.assertEqual(json.loads(json.dumps(db_point, default=json_date_serializer)), point['attributes'])

    def test_add_points_fail_missing_attr(self):
        # adding a new point must fail due to missing attribute (prop2)
        data = self.generate_random_data({'prop1': 'int'}, 5, 'point', True)
        for p in self.dataset_modifier('point', {'adds': json.dumps(data)})['addResults']:
            self.assertFalse(p.get('success'))

    def test_add_points_fail_wrong_attr(self):
        # adding new point must fail due to wrong attribute (prop3)
        data = self.generate_random_data({'prop1': 'int', 'prop3': 'int'}, 5, 'point', True)
        for p in self.dataset_modifier('point', {'adds': json.dumps(data)})['addResults']:
            self.assertFalse(p.get('success'))

    def test_add_points_fail_wrong_attr_type(self):
        # adding new point must fail die to wrong data type (str for prop2)
        data = self.generate_random_data({'prop1': 'int', 'prop2': 'str'}, 5, 'point', True)
        for p in self.dataset_modifier('point', {'adds': json.dumps(data)})['addResults']:
            self.assertFalse(p.get('success'))

    def test_add_points_success(self):
        # five new points must be added successfully
        data = self.generate_random_data({'prop1': 'int', 'prop2': 'int'}, 5, 'point', True)
        for p in self.dataset_modifier('point', {'adds': json.dumps(data)})['addResults']:
            self.assertTrue(p.get('success'))

    def test_update_points_fail_wrong_attr(self):
        # updating existing points must fail due to wrong attribute (prop3)
        data = self.generate_random_data({'prop3': 'int'}, 5)
        for idx, d in enumerate(data, 1):
            d['attributes']['db_id'] = idx
        for p in self.dataset_modifier('point', {'updates': json.dumps(data)})['updateResults']:
            self.assertFalse(p.get('success'))

    def test_update_points_fail_wrong_attr_type(self):
        # updating existing points must fail due to wrong data type (str for prop1)
        data = self.generate_random_data({'prop1': 'str'}, 5)
        for idx, d in enumerate(data, 1):
            d['attributes']['db_id'] = idx
        for p in self.dataset_modifier('point', {'updates': json.dumps(data)})['updateResults']:
            self.assertFalse(p.get('success'))

    def test_update_points_success(self):
        # updates the first 5 entries in db_point_test table with random data
        data = self.generate_random_data({'prop1': 'int'}, 5)
        for idx, d in enumerate(data, 1):
            d['attributes']['db_id'] = idx
        for p in self.dataset_modifier('point', {'updates': json.dumps(data)})['updateResults']:
            self.assertTrue(p.get('success'))

    def test_delete_points_success(self):
        # deletes the first 6 entries in db_point_test
        for p in self.dataset_modifier('point', {'deletes': '1,2,3,4,5,6'})['deleteResults']:
            self.assertTrue(p.get('success'))

    # Polyline tests
    def test_read_polylines(self):
        # makes sure data returned from api matches entries in db_polyline_test
        resp = self.client.get(API_URL_READ.format(feature_id=self.feature_service_polyline.id))
        with connection.cursor() as cur:
            for polyline in resp.json()['features']:
                cur.execute('SELECT * FROM db_polyline_test WHERE db_id = %s', (polyline['attributes']['db_id'],))
                column_names = [desc[0] for desc in cur.description]
                db_polyline = dict(zip(column_names, cur.fetchall()[0]))
                self.assertEqual(json.loads(json.dumps(db_polyline, default=json_date_serializer)),
                                 polyline['attributes'])

    def test_add_polyline_success(self):
        # five new polylines must be added successfully
        data = self.generate_random_data({'prop1': 'int', 'prop2': 'int'}, 5, 'polyline', True)
        for p in self.dataset_modifier('polyline', {'adds': json.dumps(data)})['addResults']:
            self.assertTrue(p.get('success'))

    def test_update_polyline_success(self):
        # Updates the first 5 entries in db_polyline_test table with random data
        data = self.generate_random_data({'prop1': 'int'}, 5)
        for idx, d in enumerate(data, 1):
            d['attributes']['db_id'] = idx
        for p in self.dataset_modifier('polyline', {'updates': json.dumps(data)})['updateResults']:
            self.assertTrue(p.get('success'))

    def test_delete_polylines_success(self):
        # deletes the first 6 entries in db_polyline_test
        for p in self.dataset_modifier('polyline', {'deletes': '1,2,3,4,5,6'})['deleteResults']:
            self.assertTrue(p.get('success'))

    # Polygon tests
    def test_read_polygons(self):
        # makes sure data returned from api matches the entries in db_polygon_test
        resp = self.client.get(API_URL_READ.format(feature_id=self.feature_service_polygon.id))
        with connection.cursor() as cur:
            for polygon in resp.json()['features']:
                cur.execute('SELECT * FROM db_polygon_test WHERE db_id = %s', (polygon['attributes']['db_id'],))
                column_names = [desc[0] for desc in cur.description]
                db_polygon = dict(zip(column_names, cur.fetchall()[0]))
                self.assertEqual(json.loads(json.dumps(db_polygon, default=json_date_serializer)),
                                 polygon['attributes'])

    def test_add_polygon_success(self):
        # five new polygons must be added successfully
        data = self.generate_random_data({'prop1': 'int', 'prop2': 'int'}, 5, 'polygon', True)
        for p in self.dataset_modifier('polygon', {'adds': json.dumps(data)})['addResults']:
            self.assertTrue(p.get('success'))

    def test_update_polygon_success(self):
        # Updates the first 5 entries in db_polygon_test table with random data
        data = self.generate_random_data({'prop1': 'int'}, 5)
        for idx, d in enumerate(data, 1):
            d['attributes']['db_id'] = idx
        for p in self.dataset_modifier('polygon', {'updates': json.dumps(data)})['updateResults']:
            self.assertTrue(p.get('success'))

    def test_delete_polygons_success(self):
        # deletes the first 6 entries in db_polygon_test
        for p in self.dataset_modifier('polygon', {'deletes': '1,2,3,4,5,6'})['deleteResults']:
            self.assertTrue(p.get('success'))
