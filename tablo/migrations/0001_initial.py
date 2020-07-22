# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='FeatureService',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True)),
                ('description', models.TextField(null=True)),
                ('copyright_text', models.TextField(null=True)),
                ('spatial_reference', models.CharField(max_length=255)),
                ('_initial_extent', models.TextField(db_column='initial_extent', null=True)),
                ('_full_extent', models.TextField(db_column='full_extent', null=True)),
                ('units', models.CharField(max_length=255, null=True)),
                ('allow_geometry_updates', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='FeatureServiceLayer',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True)),
                ('layer_order', models.IntegerField()),
                ('table', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=255, null=True)),
                ('description', models.TextField(null=True)),
                ('object_id_field', models.CharField(default='db_id', max_length=255)),
                ('global_id_field', models.CharField(default='db_id', max_length=255)),
                ('display_field', models.CharField(default='db_id', max_length=255)),
                ('geometry_type', models.CharField(max_length=255)),
                ('_extent', models.TextField(db_column='extent', null=True)),
                ('supports_time', models.BooleanField(default=False)),
                ('start_time_field', models.CharField(max_length=255, null=True)),
                ('_time_extent', models.TextField(db_column='time_extent', null=True)),
                ('time_interval', models.TextField(null=True)),
                ('time_interval_units', models.CharField(max_length=255, null=True)),
                ('drawing_info', models.TextField()),
                ('service', models.ForeignKey(to='tablo.FeatureService', on_delete=models.CASCADE)),
            ],
        ),
    ]
