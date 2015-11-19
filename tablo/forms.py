from django.forms import ModelForm
from tablo.models import TemporaryFile


class TemporaryFileForm(ModelForm):
    class Meta:
        model = TemporaryFile
        fields = ('file',)