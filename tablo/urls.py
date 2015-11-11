from django.conf.urls import patterns, include, url
from tastypie.api import Api

from tablo.api import FeatureServiceResource, FeatureServiceLayerResource
from tablo.views import FeatureServiceDetailView, FeatureServiceLayerDetailView, GenerateRendererView, QueryView

api = Api(api_name="v1")
api.register(FeatureServiceResource())
api.register(FeatureServiceLayerResource())

urlpatterns = patterns('')

urlpatterns += patterns('',
    url(r'^api/', include(api.urls)),
    url(r'^tablo/arcgis/rest/services/(?P<service_id>[\w\-@\._]+)/FeatureServer/?', include(patterns('',
        url(r'^$', FeatureServiceDetailView.as_view(), name='fs_arcgis_featureservice'),
        url(r'^(?P<layer_index>[0-9]+)/?', include(patterns('',
            url(r'^$', FeatureServiceLayerDetailView.as_view(), name='fs_arcgis_featureservicelayer'),
            url(r'^generateRenderer/$', GenerateRendererView.as_view(), name='fs_arcgis_generateRenderer'),
            url(r'^query', QueryView.as_view(), name='fs_arcgis_query')
        )))
    )))
)