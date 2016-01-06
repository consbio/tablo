# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tablo', '0002_temporaryfile'),
    ]

    operations = [
        migrations.AlterField(
            model_name='temporaryfile',
            name='file',
            field=models.FileField(upload_to='/ncdjango/tmp', max_length=1024),
        ),
    ]
