# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def fix_geometry_name(apps, schema_editor):
    FeatureServiceLayer = apps.get_model('tablo', 'FeatureServiceLayer')
    for layer in FeatureServiceLayer.objects.filter(geometry_type='esriGeometryPoints'):
        layer.geometry_type = 'esriGeometryPoint'
        layer.save()


class Migration(migrations.Migration):

    dependencies = [
        ('tablo', '0004_featureservicelayerrelations'),
    ]

    operations = [
        migrations.RunPython(fix_geometry_name),
    ]
