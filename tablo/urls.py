from django.conf.urls import patterns, include, url
from tastypie.api import Api

from tablo.api import FeatureServiceResource, FeatureServiceLayerResource

api = Api(api_name="feature-service")
api.register(FeatureServiceResource())
api.register(FeatureServiceLayerResource())

urlpatterns = patterns('')

urlpatterns += patterns('',
    url(r'^api/', include(api.urls))
)
