from django.conf.urls import patterns, include, url
from tastypie.api import Api

from tablo.api import FeatureServiceResource, FeatureServiceLayerResource
from tablo.interfaces.arcgis import urls as arcgis_urls

api = Api(api_name="v1")
api.register(FeatureServiceResource())
api.register(FeatureServiceLayerResource())

urlpatterns = patterns('')

urlpatterns = patterns('',
    url(r'^api/', include(api.urls)),
    url(r'^tablo/arcgis', include(arcgis_urls)),
)