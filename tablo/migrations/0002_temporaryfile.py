# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('tablo', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TemporaryFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', models.CharField(default=uuid.uuid4, max_length=36)),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('filename', models.CharField(max_length=100)),
                ('filesize', models.BigIntegerField()),
                ('file', models.FileField(max_length=1024, upload_to='/tmp')),
            ],
        ),
    ]
