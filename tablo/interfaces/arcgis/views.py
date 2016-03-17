import json
import time
import re

from django.http import HttpResponse, Http404, HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, View

from tablo.geom_utils import Extent
from tablo.models import FeatureService, FeatureServiceLayer

POINT_REGEX = re.compile('POINT\((.*) (.*)\)')


class FeatureServiceDetailView(DetailView):
    model = FeatureService
    slug_field = 'id'
    slug_url_kwarg = 'service_id'

    def render_to_response(self, context, **response_kwargs):

        data = {
            'serviceDescription': '',
            'currentVersion': 10.2,
            'supportedQueryFormats': 'JSON',
            'capabilities': 'Query',
            'supportsAdvancedQueries': True,
            'hasVersionedData': False,
            'supportsDisconnectedEditing': False,
            'maxRecordCount': 10000,
            'description': self.object.description,
            'units': self.object.units,
            'fullExtent': json.loads(self.object.full_extent),
            'initialExtent': json.loads(self.object.initial_extent),
            'spatialReference': json.loads(self.object.spatial_reference),
            'copyrightText': self.object.copyright_text,
            'allowGeometryUpdates': self.object.allow_geometry_updates,
            'layers': []
        }

        for layer in self.object.featureservicelayer_set.all():
            data['layers'].append({
                'id': layer.layer_order,
                'name': layer.name,
                'minScale': 0,
                'maxScale': 0
            })

        return HttpResponse(json.dumps(data, default=json_date_serializer), content_type='application/json')


class FeatureServiceLayerDetailView(DetailView):
    model = FeatureServiceLayer

    def get_object(self, queryset=None):
        queryset = queryset or self.get_queryset()
        service_id = self.kwargs.get('service_id')
        layer_index = self.kwargs.get('layer_index')

        return get_object_or_404(queryset, service__id=service_id, layer_order=layer_index)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.callback = request.GET.get('callback')
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def render_to_response(self, context, **response_kwargs):
        data = {
            'supportsAdvancedQueries': True,
            'supportedQueryFormats': 'JSON',
            'hasAttachments': False,
            'htmlPopupType': 'esriServerHTMLPopupTypeNone',
            'types': [],
            'templates': [],
            'type': 'Feature Layer',
            'capabilities': 'Query,Create,Delete,Update,Editing',
            'currentVersion': 10.2,
            'maxRecordCount': 10000,
            'minScale': 0,
            'maxScale': 0,
            'name': self.object.name,
            'description': self.object.description or '',
            'fields': self.object.fields,
            'drawingInfo': json.loads(self.object.drawing_info),
            'geometryType': self.object.geometry_type,
            'globalIdField': self.object.global_id_field,
            'objectIdField': self.object.object_id_field,
            'displayField': self.object.display_field,
            'extent': json.loads(self.object.extent),
            'id': self.object.layer_order
        }

        if self.object.start_time_field:
            data.update({
                'timeInfo': self.object.time_info
            })

        content = json.dumps(data, default=json_date_serializer)
        if self.callback:
            content = '{callback}({data})'.format(callback=self.callback, data=content)
        return HttpResponse(content, content_type='application/json')


class FeatureLayerView(View):
    """Base view for map service requests"""

    http_method_names = ['get', 'post', 'head', 'options']

    def __init__(self, *args, **kwargs):
        self.feature_service_layer = None
        self.callback = None

        super(FeatureLayerView, self).__init__(*args, **kwargs)

    def handle_request(self, request, **kwargs):
        """This method is called in response to either a GET or POST with GET or POST data respectively"""

        raise NotImplementedError

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):

        service_id = kwargs.get('service_id')
        layer_index = kwargs.get('layer_index')

        self.feature_service_layer = get_object_or_404(FeatureServiceLayer,
            service__id=service_id, layer_order=layer_index
        )
        return super(FeatureLayerView, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.callback = request.GET.get('callback')
        return self.handle_request(request, **request.GET.dict())

    def post(self, request, *args, **kwargs):
        self.callback = request.POST.get('callback')
        return self.handle_request(request, **request.POST.dict())


class FeatureLayerPostView(FeatureLayerView):

    def handle_request(self, request, **kwargs):
        """This method is called in response to either a GET or POST with GET or POST data respectively"""

        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class GenerateRendererView(FeatureLayerView):

    def handle_request(self, request, **kwargs):

        try:
            if 'classificationDef' not in kwargs:
                return HttpResponseBadRequest('Missing classificationDef parameter')
            classification_def = json.loads(kwargs['classificationDef'])

            if classification_def['type'] == 'uniqueValueDef':
                renderer = generate_unique_value_renderer(classification_def, self.feature_service_layer)
            elif classification_def['type'] == 'classBreaksDef':
                renderer = generate_classified_renderer(classification_def, self.feature_service_layer)
        except (ValueError, KeyError):
            return HttpResponseBadRequest(json.dumps({'error': 'Invalid request'}))

        content = json.dumps(renderer, default=json_date_serializer)
        content_type = 'application/json'
        if self.callback:
            content = '{callback}({data})'.format(callback=self.callback, data=content)
            content_type = 'text/javascript'

        return HttpResponse(content=content, content_type=content_type)


class TimeQueryView(FeatureLayerView):

    def handle_request(self, request, **kwargs):

        time_query_result = self.feature_service_layer.get_distinct_geometries_across_time()

        response = {
            'fields': [{'name': 'count', 'alias':'count', 'type': 'esriFieldTypeInteger'}],
            'geometryType': 'esriGeometryPoint',
            'count': len(time_query_result),
            'features': covert_wkt_to_esri_feature(time_query_result)
        }

        content = json.dumps(response, default=json_date_serializer)
        content_type = 'application/json'
        if self.callback:
            content = '{callback}({data})'.format(callback=self.callback, data=content)
            content_type = 'text/javascript'

        return HttpResponse(content=content, content_type=content_type)


class QueryView(FeatureLayerView):

    def handle_request(self, request, **kwargs):

        search_params = {}
        return_ids_only = kwargs.get('returnIdsOnly', 'false') in ('true', 'True')

        if 'where' in kwargs and kwargs['where'] != '':
            search_params['additional_where_clause'] = kwargs.get('where')

        if 'time' in kwargs and kwargs['time'] != '':
            start_time, end_time = kwargs['time'].split(',')
            search_params['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(float(start_time)/1000))
            search_params['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(float(end_time)/1000))

        search_params['out_sr'] = kwargs.get('outSR')

        if 'objectIds' in kwargs:
            search_params['object_ids'] = kwargs.get('objectIds', '').split(',')

        if kwargs.get('geometryType') == 'esriGeometryEnvelope':
            search_params['extent'] = Extent(json.loads(kwargs['geometry']))

        if kwargs.get('outFields') and not return_ids_only:
            search_params['return_fields'] = kwargs.get('outFields').split(',')

        if return_ids_only:
            search_params['return_fields'] = [self.feature_service_layer.object_id_field]
        elif kwargs.get('returnCountOnly', 'false') == 'true':
            search_params['only_return_count'] = True
        elif kwargs.get('returnGeometry', 'true') == 'true':
            search_params['return_geometry'] = True

        try:
            query_response = self.feature_service_layer.perform_query(**search_params)
        except ValueError:
            return HttpResponseBadRequest(json.dumps({'error': 'Invalid request'}))

        # When requesting selection IDs, ArcGIS sends both returnIdsOnly and returnCountOnly, but expects the response
        # in the 'returnIdsOnly' format
        if kwargs.get('returnIdsOnly'):
            response = {
                'count': len(query_response),
                'objectIdFieldName': self.feature_service_layer.object_id_field,
                'objectIds': [feature[self.feature_service_layer.object_id_field] for feature in query_response]
            }
        elif kwargs.get('returnCountOnly', 'false') == 'true':
            response = {'count': query_response}
        else:
            response = {
                'count': len(query_response),
                'fields': self.feature_service_layer.fields,
                'geometryType': 'esriGeometryPoint',
                'features': covert_wkt_to_esri_feature(query_response)
            }

        content = json.dumps(response, default=json_date_serializer)
        content_type = 'application/json'
        if self.callback:
            content = '{callback}({data})'.format(callback=self.callback, data=content)
            content_type = 'text/javascript'

        return HttpResponse(content=content, content_type=content_type)


def generate_unique_value_renderer(classification_def, layer):
    unique_field = classification_def['uniqueValueFields'][0]
    unique_value_infos = [{'value': value} for value in layer.get_unique_values(unique_field)]
    return {
        'type': 'uniqueValue',
        'field1': unique_field,
        'uniqueValueInfos': unique_value_infos
    }


def generate_classified_renderer(classification_def, layer):
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


def covert_wkt_to_esri_feature(response_items):
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
            features.append({'attributes': query_response_dict})
    return features


def json_date_serializer(obj):
    # Handles date serialization when part of the response object

    if hasattr(obj, 'isoformat'):
        serial = obj.isoformat()
        return serial
    return json.JSONEncoder.default(obj)


class AddFeaturesView(FeatureLayerView):

    def handle_request(self, request, **kwargs):

        features = json.loads(kwargs.get('features', []))
        rollback_on_failure = kwargs.get('rollbackOnFailure', True)

        response_obj = []
        for feature in features:
            try:
                object_id = self.feature_service_layer.add_feature(feature)
                response_obj.append({
                    'objectId': object_id,
                    'success': True
                })
            except Exception as e:
                response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error adding feature: ' + str(e)
                    }
                })

        content = json.dumps({'addResults': response_obj}, default=json_date_serializer)
        content_type = 'application/json'
        if self.callback:
            content = '{callback}({data})'.format(callback=self.callback, data=content)
            content_type = 'text/javascript'

        return HttpResponse(content=content, content_type=content_type)


class UpdateFeaturesView(FeatureLayerView):

    def handle_request(self, request, **kwargs):
        features = json.loads(kwargs.get('features', []))
        rollback_on_failure = kwargs.get('rollbackOnFailure', True)

        response_obj = []
        for feature in features:
            try:
                object_id = self.feature_service_layer.update_feature(feature)
                response_obj.append({
                    'objectId': object_id,
                    'success': True
                })
            except Exception as e:
                response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error updating feature: ' + str(e)
                    }
                })

        content = json.dumps({'editResults': response_obj}, default=json_date_serializer)
        content_type = 'application/json'
        if self.callback:
            content = '{callback}({data})'.format(callback=self.callback, data=content)
            content_type = 'text/javascript'

        return HttpResponse(content=content, content_type=content_type)


class DeleteFeaturesView(FeatureLayerView):

    def handle_request(self, request, **kwargs):

        response_obj = []
        for object_id in kwargs['objectIds'].split(','):
            try:
                object_id = self.feature_service_layer.delete_feature(object_id)
                response_obj.append({
                    'objectId': object_id,
                    'success': True
                })
            except Exception as e:
                response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error deleting feature: ' + str(e)
                    }
                })

        content = json.dumps({'deleteResponse': response_obj}, default=json_date_serializer)
        content_type = 'application/json'
        if self.callback:
            content = '{callback}({data})'.format(callback=self.callback, data=content)
            content_type = 'text/javascript'

        return HttpResponse(content=content, content_type=content_type)


class ApplyEditsView(FeatureLayerView):

    def handle_request(self, request, **kwargs):
        adds = json.loads(kwargs.get('adds', '[]'))
        updates = json.loads(kwargs.get('updates', '[]'))
        delete_list = kwargs.get('deletes', None)
        deletes = str(delete_list).split(',') if delete_list else []

        add_response_obj = []
        for feature in adds:
            try:
                object_id = self.feature_service_layer.add_feature(feature)
                add_response_obj.append({
                    'objectId': object_id,
                    'success': True
                })
            except Exception as e:
                add_response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error adding feature: ' + str(e)
                    }
                })

        update_response_obj = []
        for feature in updates:
            try:
                object_id = self.feature_service_layer.update_feature(feature)
                update_response_obj.append({
                    'objectId': object_id,
                    'success': True
                })
            except Exception as e:
                update_response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error updating feature: ' + str(e)
                    }
                })

        delete_response_obj = []
        for object_id in deletes:
            try:
                object_id = self.feature_service_layer.delete_feature(object_id)
                delete_response_obj.append({
                    'objectId': object_id,
                    'success': True
                })
            except Exception as e:
                delete_response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error deleting feature: ' + str(e)
                    }
                })

        content = json.dumps({
            'addResults': add_response_obj,
            'updateResults': update_response_obj,
            'deleteResults': delete_response_obj
        }, default=json_date_serializer)
        content_type = 'application/json'
        if self.callback:
            content = '{callback}({data})'.format(callback=self.callback, data=content)
            content_type = 'text/javascript'

        return HttpResponse(content=content, content_type=content_type)