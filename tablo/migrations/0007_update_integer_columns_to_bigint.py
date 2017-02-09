# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from tablo.models import PRIMARY_KEY_NAME


def convert_to_bigint(apps, schema_editor):
    _alter_columns(apps, schema_editor)


def convert_to_integer(apps, schema_editor):
    _alter_columns(apps, schema_editor, convert_to='integer', convert_from='bigint')


def _alter_columns(apps, schema_editor, convert_to='bigint', convert_from='integer'):

    # For datasets that have DDL in transactions, migrations are done in a single transaction
    # The size of the changes here will cause this to fail on larger databases (such as development and production)
    # Break out of the atomic nature, allowing us to commit after every table
    schema_editor.atomic.__exit__(None, None, None)

    FeatureServiceLayer = apps.get_model('tablo', 'FeatureServiceLayer')

    for layer in FeatureServiceLayer.objects.all():
        table_query = (
                'SELECT column_name FROM information_schema.columns '
                'WHERE table_name = %s AND column_name != %s AND data_type = %s'
        )
        cursor = schema_editor.connection.cursor()
        cursor.execute(table_query, [layer.table, PRIMARY_KEY_NAME, convert_from])

        for row in cursor:
            alter_operation = 'ALTER TABLE {0} ALTER COLUMN {1} TYPE {2}'.format(layer.table, row[0], convert_to)
            print(alter_operation)
            schema_editor.execute(alter_operation)

        schema_editor.connection.commit()


class Migration(migrations.Migration):

    dependencies = [
        ('tablo', '0006_alter_geom_col_type'),
    ]

    # The reverse operation is just for test in development; a reverse migration can throw an error if tables contain
    # integer values bigger than 2147483647. So after pushing this migration to production, rolling back should be
    # avoided.
    operations = [
        migrations.RunPython(convert_to_bigint, convert_to_integer)
    ]
