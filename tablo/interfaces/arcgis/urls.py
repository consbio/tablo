from django.conf.urls import patterns, include, url

from tablo.interfaces.arcgis.views import FeatureServiceDetailView, FeatureServiceLayerDetailView, GenerateRendererView
from tablo.interfaces.arcgis.views import QueryView, TimeQueryView
from tablo.interfaces.arcgis.views import AddFeaturesView, UpdateFeaturesView, DeleteFeaturesView, ApplyEditsView

urlpatterns = patterns('',
    url(r'rest/services/(?P<service_id>[\w\-@\._]+)/FeatureServer/?', include(patterns('',
        url(r'^$', FeatureServiceDetailView.as_view(), name='fs_arcgis_featureservice'),
        url(r'^(?P<layer_index>[0-9]+)/?', include(patterns('',
            url(r'^$', FeatureServiceLayerDetailView.as_view(), name='fs_arcgis_featureservicelayer'),
            url(r'^generateRenderer', GenerateRendererView.as_view(), name='fs_arcgis_generateRenderer'),
            url(r'^query', QueryView.as_view(), name='fs_arcgis_query'),
            url(r'^time-query', TimeQueryView.as_view(), name='fs_arcgis_time_query'),
            url(r'^addFeatures', AddFeaturesView.as_view(), name='add_features'),
            url(r'^updateFeatures', UpdateFeaturesView.as_view(), name='fs_arcgis_time_query'),
            url(r'^deleteFeatures', DeleteFeaturesView.as_view(), name='fs_arcgis_time_query'),
            url(r'^applyEdits', ApplyEditsView.as_view(), name='fs_arcgis_time_query'),
        )))
    )))
)