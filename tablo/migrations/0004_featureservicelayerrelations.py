# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tablo', '0003_auto_20160106_1509'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeatureServiceLayerRelations',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('related_index', models.PositiveIntegerField(default=0)),
                ('related_title', models.CharField(max_length=255)),
                ('source_column', models.CharField(max_length=255)),
                ('target_column', models.CharField(max_length=255)),
                ('layer', models.ForeignKey(to='tablo.FeatureServiceLayer')),
            ],
        ),
    ]
