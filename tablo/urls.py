from django.conf.urls import include, url
from tastypie.api import Api

from .api import FeatureServiceResource, FeatureServiceLayerResource, FeatureServiceLayerRelationsResource
from .api import TemporaryFileResource
from .views import TemporaryFileUploadFormView, TemporaryFileUploadUrlView
from .interfaces.arcgis import urls as arcgis_urls


api = Api(api_name='v1')
api.register(FeatureServiceResource())
api.register(FeatureServiceLayerResource())
api.register(FeatureServiceLayerRelationsResource())
api.register(TemporaryFileResource())

app_name = 'tablo'

urlpatterns = [
    url(r'^api/', include(api.urls)),
    url(r'^tablo/arcgis/', include(arcgis_urls)),
    url(r'^tablo/admin/upload-by-url/$', TemporaryFileUploadUrlView.as_view(), name='tablo_admin_upload_by_url'),
    url(r'^tablo/admin/upload/$', TemporaryFileUploadFormView.as_view(), name='tablo_admin_upload')
]
