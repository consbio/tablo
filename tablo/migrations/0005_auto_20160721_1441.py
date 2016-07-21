# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tablo', '0004_featureservicelayerrelations'),
    ]

    operations = [
        migrations.AddField(
            model_name='featureservicelayerrelations',
            name='source_column',
            field=models.CharField(max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='featureservicelayerrelations',
            name='target_column',
            field=models.CharField(max_length=255),
            preserve_default=False,
        ),
    ]
