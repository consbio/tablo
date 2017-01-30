# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from tablo.models import PRIMARY_KEY_NAME

sql = """
DO
$$
DECLARE
    table_name name;
    column_name name;
BEGIN
FOR table_name IN
    SELECT tablo_featureservicelayer.table FROM tablo_featureservicelayer
LOOP
    FOR column_name IN
        EXECUTE format(
            'SELECT column_name FROM information_schema.columns
            WHERE table_name = %L AND column_name != ''{primary_key}'' AND data_type = ''{convert_from}'';',
            table_name
        )
    LOOP
        EXECUTE format('ALTER TABLE %I ALTER COLUMN %I TYPE {convert_to};', table_name, column_name);
    END LOOP;
END LOOP;
END;
$$
LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [
        ('tablo', '0006_alter_geom_col_type'),
    ]

    # The reverse sql is just for test in development; a reverse migration can throw an error if tables contain integer
    # values bigger than 2147483647. So after pushing this migration to production, rolling back should be avoided.
    operations = [
        migrations.RunSQL(
            sql=sql.format(primary_key=PRIMARY_KEY_NAME, convert_from='integer', convert_to='bigint'),
            reverse_sql=sql.format(primary_key=PRIMARY_KEY_NAME, convert_from='bigint', convert_to='integer')
        )
    ]
