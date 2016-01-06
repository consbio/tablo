import json
import shutil
import tempfile
import six

from urllib.error import URLError

from django.core.files import File
from django.http import HttpResponseBadRequest, HttpResponse
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View
from django.views.generic.edit import ProcessFormView, FormMixin

from tablo.forms import TemporaryFileForm
from tablo.models import TemporaryFile


class TemporaryFileUploadViewBase(View):
    @method_decorator(login_required)
    @method_decorator(permission_required('tablo.add_temporaryfile'))
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(TemporaryFileUploadViewBase, self).dispatch(request, *args, **kwargs)

    def process_temporary_file(self, tmp_file):
        """Truncates the filename if necessary, saves the model, and returns a response"""

        #Truncate filename if necessary
        if len(tmp_file.filename) > 100:
            base_filename = tmp_file.filename[:tmp_file.filename.rfind(".")]
            tmp_file.filename = "%s.%s" % (base_filename[:99-len(tmp_file.extension)], tmp_file.extension)

        tmp_file.save()

        data = {
            'uuid': str(tmp_file.uuid)
        }

        response = HttpResponse(json.dumps(data), status=201)
        response['Content-type'] = "text/plain"

        return response


class TemporaryFileUploadFormView(FormMixin, TemporaryFileUploadViewBase, ProcessFormView):
    form_class = TemporaryFileForm

    def form_valid(self, form):
        tmp_file = form.save(commit=False)
        tmp_file.filename = self.request.FILES['file'].name
        tmp_file.filesize = self.request.FILES['file'].size

        return self.process_temporary_file(tmp_file)

    def form_invalid(self, form):
        return HttpResponseBadRequest()


class TemporaryFileUploadUrlView(TemporaryFileUploadViewBase):
    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        try:
            return super(TemporaryFileUploadUrlView, self).dispatch(request, *args, **kwargs)
        except URLError as e:
            return HttpResponseBadRequest('{0}{1}'.format(request.POST.get('url'), e.reason))

    def download_file(self, url):

        url_f = six.moves.urllib.request.urlopen(url)

        filename = url.split('?', 1)[0].split('/')[-1]
        if 'filename=' in url_f.info().get('Content-Disposition', ''):
            filename = url_f.info()['Content-Disposition'].split('filename=')[-1].strip('"\'')

        f = tempfile.TemporaryFile()
        shutil.copyfileobj(url_f, f)

        tmp_file = TemporaryFile(
            filename=filename
        )
        tmp_file.file.save(filename, File(f), save=False)
        tmp_file.filesize = tmp_file.file.size

        return tmp_file

    def get(self, request):
        if request.GET.get('url'):
            return self.process_temporary_file(self.download_file(six.moves.urllib.parse.unquote(request.GET.get('url'))))
        else:
            return HttpResponseBadRequest('Missing URL')

    def post(self, request):
        if request.POST.get('url'):
            return self.process_temporary_file(self.download_file(request.POST.get('url')))
        else:
            return self.get(request)
