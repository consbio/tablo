import json
import logging
import re
import time

from django.conf.urls import url
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.http import Http404

from tastypie import fields
from tastypie.constants import ALL
from tastypie.http import HttpMultipleChoices, HttpBadRequest
from tastypie.resources import ModelResource
from tastypie.serializers import Serializer

from tablo.models import FeatureService, FeatureServiceLayer
from tablo.utils import JSONField
from tablo.geom_utils import Extent


# For FeatureServiceResource and FeatureServiceLayerResource, I tried to use a camel case serializer, but we
# don't want certain lower-level items processed in this manner -- such as the actual database column names for
# field names, so I have 'hand-coded' which values need to be camelized

POINT_REGEX = re.compile('POINT\((.*) (.*)\)')

logger = logging.getLogger(__name__)


class FeatureServiceResource(ModelResource):
    fullExtent = JSONField(attribute="full_extent")
    initialExtent = JSONField(attribute="initial_extent")
    spatialReference = JSONField(attribute="spatial_reference")
    copyrightText = fields.CharField(attribute='copyright_text', null=True)
    allowGeometryUpdates = fields.BooleanField(attribute='allow_geometry_updates')

    class Meta:
        object_class = FeatureService
        resource_name = 'featureservice'
        detail_allowed_methods = ['get']
        fields = ['fullExtent', 'initialExtent', 'spatialReference', 'description', 'copyrightText', 'units',
                  'allowGeometryUpdates']
        serializer = Serializer(formats=['json', 'jsonp'])
        queryset = FeatureService.objects.all()

    def prepend_urls(self):
        return [
            url(
                r'^(?P<resource_name>{0})/(?P<service_id>[\w\-@\._]+)/FeatureServer/(?P<layer_order>\d+)/generateRenderer'.format(
                    self._meta.resource_name
                ), self.wrap_view('generate_renderer'), name="api_feature_service_layer_generate_renderer"
            ),
            url(
                r'^(?P<resource_name>{0})/(?P<service_id>[\w\-@\._]+)/FeatureServer/(?P<layer_order>\d+)/query'.format(
                    self._meta.resource_name
                ), self.wrap_view('perform_query'), name="api_feature_service_layer_query"
            ),
            url(
                r'^(?P<resource_name>{0})/(?P<service_id>[\w\-@\._]+)/FeatureServer/(?P<layer_order>\d+)'.format(
                    self._meta.resource_name
                ), self.wrap_view('dispatch_child'), name="api_dispatch_child"
            ),
            url(
                r'^(?P<resource_name>{0})/(?P<id>[\w\-@\._]+)/FeatureServer'.format(
                    self._meta.resource_name
                ), self.wrap_view('dispatch_detail'), name="api_dispatch_detail"
            )

        ]

    def dispatch_child(self, request, **kwargs):
        return FeatureServiceLayerResource().dispatch('detail', request, **kwargs)

    def perform_query(self, request, **kwargs):
        return FeatureServiceLayerResource().perform_query(request, **kwargs)

    def generate_renderer(self, request, **kwargs):
        return FeatureServiceLayerResource().generate_renderer(request, **kwargs)

    def dehydrate(self, bundle):
        bundle.data['layers'] = []

        for layer in bundle.obj.featureservicelayer_set.all():
            bundle.data['layers'].append({
                'id': layer.layer_order,
                'name': layer.name,
                'minScale': 0,
                'maxScale': 0
            })

        # Hard-coded values for all feature services
        bundle.data.update({
            'serviceDescription': '',
            'currentVersion': 10.2,
            'supportedQueryFormats': 'JSON',
            'capabilities': 'Query',
            'supportsAdvancedQueries': True,
            'hasVersionedData': False,
            'supportsDisconnectedEditing': False,
            'maxRecordCount': 10000
        })

        return bundle


class FeatureServiceLayerResource(ModelResource):

    drawingInfo = JSONField(attribute='drawing_info')
    geometryType = fields.CharField(attribute='geometry_type')
    globalIdField = fields.CharField(attribute='global_id_field')
    objectIdField = fields.CharField(attribute='object_id_field')
    displayField = fields.CharField(attribute='display_field')
    extent = JSONField(attribute='extent')

    timeInfo = fields.DictField(attribute='time_info', null=True, blank=True)
    id = fields.IntegerField(attribute='layer_order')
    fields = fields.ListField(attribute='fields')

    class Meta:
        object_class = FeatureServiceLayer
        resource_name = 'featureservicelayer'
        filtering = {'layer_order': ALL}
        detail_allowed_methods = ['get']
        fields = ['name', 'description', 'extent', 'fields', 'timeInfo']
        serializer = Serializer(formats=['json', 'jsonp'])
        queryset = FeatureServiceLayer.objects.all()

    def dehydrate(self, bundle):
        # Do not return timeInfo: null, just remove the property if it's None
        if bundle.data['timeInfo'] is None:
            del bundle.data['timeInfo']
        bundle.data.update({
            'supportsAdvancedQueries': True,
            'supportedQueryFormats': 'JSON',
            'hasAttachments': False,
            'htmlPopupType': 'esriServerHTMLPopupTypeNone',
            'types': [],
            'templates': [],
            'type': 'Feature Layer',
            'capabilities': 'Query',
            'currentVersion': 10.2,
            'minScale': 0,
            'maxScale': 0
        })
        return bundle

    def perform_query(self, request, **kwargs):
        try:
            bundle = self.build_bundle(data={'service_id': kwargs['service_id'], 'layer_order': 0}, request=request)
            layer = self.cached_obj_get(bundle=bundle, **self.remove_api_resource_names(kwargs))
        except ObjectDoesNotExist:
            return Http404()
        except MultipleObjectsReturned:
            return HttpMultipleChoices("More than one resource is found at this URI.")

        search_params = {}
        return_ids_only = request.REQUEST.get('returnIdsOnly', 'false') == 'true'

        if 'where' in request.REQUEST and request.REQUEST['where'] != '':
            search_params['additional_where_clause'] = request.REQUEST.get('where')

        if 'time' in request.REQUEST and request.REQUEST['time'] != '':
            start_time, end_time = request.REQUEST['time'].split(',')
            search_params['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(float(start_time)/1000))
            search_params['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(float(end_time)/1000))

        if request.REQUEST.get('geometryType') == 'esriGeometryEnvelope':
            search_params['extent'] = Extent(json.loads(request.REQUEST['geometry']))

        if request.REQUEST.get('outFields') and not return_ids_only:
            search_params['return_fields'] = request.REQUEST.get('outFields').split(',')

        if return_ids_only:
            search_params['return_fields'] = [layer.object_id_field]
        elif request.REQUEST.get('returnCountOnly', 'false') == 'true':
            search_params['only_return_count'] = True
        elif request.REQUEST.get('returnGeometry', 'true') == 'true':
            search_params['return_geometry'] = True

        try:
            query_response = layer.perform_query(**search_params)
        except ValueError:
            logger.exception('Error in perform_query')
            return HttpBadRequest(json.dumps({'error': 'Invalid request'}))


        # When requesting selection IDs, ArcGIS sends both returnIdsOnly and returnCountOnly, but expects the response
        # in the 'returnIdsOnly' format
        if request.REQUEST.get('returnIdsOnly'):
            response = {
                'count': len(query_response),
                'objectIdFieldName': layer.object_id_field,
                'objectIds': [feature[layer.object_id_field] for feature in query_response]
            }
        elif request.REQUEST.get('returnCountOnly', 'false') == 'true':
            response = {'count': query_response}
        else:
            response = {
                'count': len(query_response),
                'fields': layer.fields,
                'geometryType': 'esriGeometryPoint',
                'features': self.covert_wkt_to_esri_feature(query_response)
            }

        return self.create_response(request, response)

    def generate_renderer(self, request, **kwargs):
        try:
            bundle = self.build_bundle(data={'service_id': kwargs['service_id'], 'layer_order': 0}, request=request)
            layer_obj = self.cached_obj_get(bundle=bundle, **self.remove_api_resource_names(kwargs))
        except ObjectDoesNotExist:
            return Http404()
        except MultipleObjectsReturned:
            return HttpMultipleChoices("More than one resource is found at this URI.")

        try:
            if 'classificationDef' not in request.REQUEST:
                return HttpBadRequest('Missing classificationDef parameter')
            classification_def = json.loads(request.REQUEST['classificationDef'])

            renderer = {}
            if classification_def['type'] == 'uniqueValueDef':
                renderer = self.generate_unique_value_renderer(classification_def, layer_obj)
            elif classification_def['type'] == 'classBreaksDef':
                renderer = self.generate_classified_renderer(classification_def, layer_obj)
        except (ValueError, KeyError):
            return HttpBadRequest(json.dumps({'error': 'Invalid request'}))

        return self.create_response(request, renderer)

    def generate_unique_value_renderer(self, classification_def, layer):
        unique_field = classification_def['uniqueValueFields'][0]
        unique_value_infos = [{'value': value} for value in layer.get_unique_values(unique_field)]
        return {
            'type': 'uniqueValue',
            'field1': unique_field,
            'uniqueValueInfos': unique_value_infos
        }

    def generate_classified_renderer(self, classification_def, layer):
        field = classification_def['classificationField']
        method = classification_def['classificationMethod']
        break_count = int(classification_def['breakCount'])

        breaks = []
        if method == 'esriClassifyEqualInterval':
            breaks = layer.get_equal_breaks(field, break_count)
        elif method == 'esriClassifyQuantile':
            breaks = layer.get_quantile_breaks(field, break_count)
        elif method == 'esriClassifyNaturalBreaks':
            breaks = layer.get_natural_breaks(field, break_count)

        class_break_infos = []
        current_min = breaks[0]
        for break_info in breaks[1:]:
            class_break_infos.append({
                'classMinValue': current_min,
                'classMaxValue': break_info
            })
            current_min = break_info

        return {
            'type': 'classBreaks',
            'field': field,
            'classificationMethod': method,
            'minValue': breaks[0],
            'classBreakInfos': class_break_infos
        }

    def covert_wkt_to_esri_feature(self, response_items):
        features = []
        for query_response_dict in response_items:
            # This only currently works for points
            if 'st_astext' in query_response_dict:
                point_text = query_response_dict['st_astext']
                match = POINT_REGEX.match(point_text)
                if not match:
                    raise ValueError('Invalid Point Geometry: {0}'.format(point_text))

                x, y = (float(x) for x in match.groups())
                query_response_dict.pop('st_astext')
                features.append({
                    'attributes': query_response_dict,
                    'geometry': {
                        'x': x,
                        'y': y
                    }
                })
            else:
                features.append({'attributes':query_response_dict})
        return features


