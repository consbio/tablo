from django.conf.urls import include, url

from .views import FeatureServiceDetailView, FeatureServiceLayerDetailView, GenerateRendererView
from .views import QueryView, TimeQueryView, ImageView


urlpatterns = [
    url(
        r'rest/services/(?P<service_id>[\w\-@\._]+)/FeatureServer/?',
        include([
            url(r'^$', FeatureServiceDetailView.as_view(), name='fs_arcgis_featureservice'),
            url(r'^(?P<layer_index>[0-9]+)/?', include([
                url(r'^$', FeatureServiceLayerDetailView.as_view(), name='fs_arcgis_featureservicelayer'),
                url(r'^generateRenderer', GenerateRendererView.as_view(), name='fs_arcgis_generateRenderer'),
                url(r'^query', QueryView.as_view(), name='fs_arcgis_query'),
                url(r'^time-query', TimeQueryView.as_view(), name='fs_arcgis_time_query'),
                url(
                    r'^image/(?P<entry_id>(\d+))/(?P<col_name>[\w\-]+)/$',
                    view=ImageView.as_view(),
                    name='fs_arcgis_image_view'
                ),
            ]))
        ])
    )
]
