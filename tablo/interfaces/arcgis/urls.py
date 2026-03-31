from django.urls import include, re_path

from .views import FeatureServiceDetailView, FeatureServiceLayerDetailView, GenerateRendererView
from .views import QueryView, TimeQueryView, ImageView


urlpatterns = [
    re_path(
        r"rest/services/(?P<service_id>[\w\-@\._]+)/FeatureServer/?",
        include(
            [
                re_path(
                    r"^$",
                    FeatureServiceDetailView.as_view(),
                    name="fs_arcgis_featureservice",
                ),
                re_path(
                    r"^(?P<layer_index>[0-9]+)/?",
                    include(
                        [
                            re_path(
                                r"^$",
                                FeatureServiceLayerDetailView.as_view(),
                                name="fs_arcgis_featureservicelayer",
                            ),
                            re_path(
                                r"^generateRenderer",
                                GenerateRendererView.as_view(),
                                name="fs_arcgis_generateRenderer",
                            ),
                            re_path(
                                r"^query", QueryView.as_view(), name="fs_arcgis_query"
                            ),
                            re_path(
                                r"^time-query",
                                TimeQueryView.as_view(),
                                name="fs_arcgis_time_query",
                            ),
                            re_path(
                                r"^image/(?P<entry_id>(\d+))/(?P<col_name>[\w\-]+)/$",
                                view=ImageView.as_view(),
                                name="fs_arcgis_image_view",
                            ),
                        ]
                    ),
                ),
            ]
        ),
    )
]
