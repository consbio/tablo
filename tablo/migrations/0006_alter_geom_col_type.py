# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from tablo.models import GEOM_FIELD_NAME, WEB_MERCATOR_SRID

forward_sql = """
    DO
    $$
    DECLARE
        table_name name;
    BEGIN
        FOR table_name IN
            SELECT tablo_featureservicelayer.table FROM tablo_featureservicelayer
        LOOP
            EXECUTE format('ALTER TABLE %I ALTER COLUMN {geom_col} TYPE geometry(''GEOMETRY'', {srid});', table_name);
        END LOOP;
    END;
    $$
    LANGUAGE plpgsql;
    """.format(geom_col=GEOM_FIELD_NAME, srid=WEB_MERCATOR_SRID)

# FIXME In case of reverse, shall we drop non-point datasets and their relevant featureservice(layers)?
reverse_sql = """
    DO
    $$
    DECLARE
        table_name name;
    BEGIN
        FOR table_name IN
            SELECT tablo_featureservicelayer.table FROM tablo_featureservicelayer WHERE geometry_type = 'esriGeometryPoint'
        LOOP
            EXECUTE format('ALTER TABLE %I ALTER COLUMN {geom_col} TYPE geometry(''POINT'', {srid});', table_name);
        END LOOP;
    END;
    $$
    LANGUAGE plpgsql;
""".format(geom_col=GEOM_FIELD_NAME, srid=WEB_MERCATOR_SRID)


class Migration(migrations.Migration):
    dependencies = [
        ('tablo', '0005_fix_esriGeometryPoints'),
    ]

    operations = [
        migrations.RunSQL(forward_sql, reverse_sql)
    ]
