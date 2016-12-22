from django.db import connection
from django.test import TestCase

from tablo import wkt


class TestWKT(TestCase):

    def setUp(self):
        super(TestWKT, self).setUp()

        with open('tablo/tests/tables.sql', 'r') as sql:
            with connection.cursor() as cur:
                cur.execute(sql.read())

    def test_point(self):
        with connection.cursor() as cur:
            cur.execute('SELECT ST_AsText(dbasin_geom), ST_AsEWKT(dbasin_geom) FROM db_point_test')
            points = cur.fetchall()
            for p in points:
                self.assertEqual(wkt.from_esri_feature(wkt.to_esri_feature(p[0]), 'esriGeometryPoint'), p[1])

    def test_polyline(self):
        with connection.cursor() as cur:
            cur.execute('SELECT ST_AsText(dbasin_geom), ST_AsEWKT(ST_Multi(dbasin_geom)) FROM db_polyline_test')
            polylines = cur.fetchall()
            for pl in polylines:
                self.assertEqual(wkt.from_esri_feature(wkt.to_esri_feature(pl[0]), 'esriGeometryPolyline'), pl[1])

    def test_polygon(self):
        # ST_ForceRHR (Force Right Hand Rule) is used to make postgis result compatible with ESRI polygon orientation,
        # i.e. clockwise for exterior rings.
        # ST_Multi is used, because wkt returns multi geometries
        with connection.cursor() as cur:
            cur.execute(
                'SELECT ST_AsText(dbasin_geom), ST_AsEWKT(ST_ForceRHR(ST_Multi(dbasin_geom))) FROM db_polygon_test'
            )
            polygons = cur.fetchall()
            for pg in polygons:
                self.assertEqual(wkt.from_esri_feature(wkt.to_esri_feature(pg[0]), 'esriGeometryPolygon'), pg[1])
