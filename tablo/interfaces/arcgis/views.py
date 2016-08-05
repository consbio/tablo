import json
import logging
import time
import re

from django.db.utils import DatabaseError
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, View

from tablo.geom_utils import Extent
from tablo.models import FeatureService, FeatureServiceLayer

POINT_REGEX = re.compile('POINT\((.*) (.*)\)')

logger = logging.getLogger(__name__)


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
            'capabilities': 'Query',
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

        data['relatedTables'] = [
            {
                'name': r.related_title,
                'fields': [{'name': f['name'], 'type': f['type']} for f in r.fields]
            } for r in self.object.relations
        ]

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

        self.feature_service_layer = get_object_or_404(
            FeatureServiceLayer, service__id=service_id, layer_order=layer_index
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

        features = convert_wkt_to_esri_feature(time_query_result, self.feature_service_layer)
        response = {
            'count': len(features),           # Root level (source) features
            'total': len(time_query_result),  # Total number of records queried
            'fields': [{'name': 'count', 'alias': 'count', 'type': 'esriFieldTypeInteger'}],
            'geometryType': 'esriGeometryPoint',
            'features': features
        }

        content = json.dumps(response, default=json_date_serializer)
        content_type = 'application/json'
        if self.callback:
            content = '{callback}({data})'.format(callback=self.callback, data=content)
            content_type = 'text/javascript'

        return HttpResponse(content=content, content_type=content_type)


class QueryView(FeatureLayerView):
    query_limit_default = 50000

    def handle_request(self, request, **kwargs):

        search_params = {}
        limit, offset = int(kwargs.get('limit', self.query_limit_default)), int(kwargs.get('offset', 0))

        # Capture format type: default anything but csv or json to json
        valid_formats = {'csv', 'json'}
        return_format = kwargs.get('f', 'json').lower()
        return_format = return_format if return_format in valid_formats else 'json'

        # When requesting IDs, ArcGIS sends returnIdsOnly AND returnCountOnly, but expects the IDs response
        return_ids_only = return_format == 'json' and kwargs.get('returnIdsOnly', 'false').lower() == 'true'
        return_count_only = not return_ids_only and kwargs.get('returnCountOnly', 'false').lower() == 'true'

        if 'where' in kwargs and kwargs['where'] != '':
            search_params['additional_where_clause'] = kwargs.get('where')

        if 'time' in kwargs and kwargs['time'] != '':
            start_time, end_time = kwargs['time'].split(',')
            search_params['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(float(start_time) / 1000))
            search_params['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(float(end_time) / 1000))

        search_params['out_sr'] = kwargs.get('outSR')

        if 'objectIds' in kwargs:
            search_params['object_ids'] = (kwargs['objectIds'] or '').split(',')

        if kwargs.get('geometryType') == 'esriGeometryEnvelope':
            search_params['extent'] = Extent(json.loads(kwargs['geometry']))

        if not return_ids_only and kwargs.get('outFields'):
            search_params['return_fields'] = (kwargs['outFields'] or '').split(',')

        if not return_ids_only and kwargs.get('orderByFields'):
            search_params['order_by_fields'] = (kwargs['orderByFields'] or '').split(',')

        if return_format == 'csv':
            search_params['return_geometry'] = False
        elif return_ids_only:
            search_params['return_fields'] = [self.feature_service_layer.object_id_field]
            search_params['return_geometry'] = False
        elif return_count_only:
            search_params['count_only'] = True
        elif kwargs.get('returnGeometry', 'true').lower() == 'false':
            search_params['return_geometry'] = False

        try:
            # Query with limit plus one to determine if the limit excluded any features
            query_response = self.feature_service_layer.perform_query(int(limit) + 1, offset, **search_params)
        except (DatabaseError, ValueError):
            return HttpResponseBadRequest(json.dumps({'error': 'Invalid request'}))

        # Process limited query before calculating totals and counts
        exceeded_limit = len(query_response) > int(limit)
        query_response = query_response[:-1] if exceeded_limit else query_response

        if return_count_only:
            data = query_response[0]
        elif return_format == 'csv':
            header = list(query_response[0].keys())
            header.sort()

            data = [[h.strip('"').join('""') for h in header]] if offset == 0 else []
            for item in query_response:
                data.append([str(item[field]).strip('"').join('""') for field in header])
        else:
            data = {
                'count': len(query_response),
                'total': len(query_response),
                'exceededTransferLimit': exceeded_limit
            }
            if return_ids_only:
                object_id_field = self.feature_service_layer.object_id_field
                data['objectIdFieldName'] = object_id_field
                data['objectIds'] = [feature[object_id_field] for feature in query_response]
            else:
                features = convert_wkt_to_esri_feature(query_response, self.feature_service_layer)
                data.update({
                    'count': len(features),        # Root level (source) features
                    'total': len(query_response),  # Total number of records queried
                    'fields': self.feature_service_layer.fields,
                    'geometryType': 'esriGeometryPoint',
                    'features': features
                })

                if data['total'] > data['count']:
                    data['relatedFields'] = {
                        r.related_title: r.fields for r in self.feature_service_layer.relations
                    }

        if return_format == 'csv':
            content = '\n'.join(','.join(col if isinstance(col, str) else str(col) for col in row) for row in data)
            content_type = 'text/csv'
        else:
            content = json.dumps(data, default=json_date_serializer)

            if not self.callback:
                content_type = 'application/json'
            else:
                content = '{callback}({data})'.format(callback=self.callback, data=content)
                content_type = 'text/javascript'

        response = HttpResponse(content=content, content_type=content_type)
        if content_type == 'text/csv':
            response['Content-Disposition'] = 'attachment; filename="query.csv"'

        return response


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


def convert_wkt_to_esri_feature(response_items, for_layer):

    if not response_items:
        return []

    # Gather related table information to ensure fields are correctly represented

    query_fields = {f for f in response_items[0]}
    layer_fields = {f['name'] for f in for_layer.fields if f['name'] in query_fields}
    layer_fields.add('id')  # Ensures related items are placed correctly even when fk appears more than once in source

    joined_tables = {
        r.related_title: {
            'source': r.source_column,
            'target': r.target_column,
            'fields': {f['name'] for f in r.fields if f['name'] in query_fields}
        } for r in for_layer.relations
    }
    joined_tables = {k: v for k, v in joined_tables.items() if v['fields']}

    # Loop over queried items and construct feature response

    item_hash_format = 'id:{id}.{fk}:{val}.{table}'
    already_added = {}
    features = []

    for item in response_items:
        feature = {'attributes': item, 'related': {'count': 0}}

        if 'st_astext' in item:
            # This only currently works for points

            point_text = item.pop('st_astext')
            match = POINT_REGEX.match(point_text)
            if not match:
                raise ValueError('Invalid Point Geometry: {0}'.format(point_text))

            x, y = (float(x) for x in match.groups())
            feature['geometry'] = {'x': x, 'y': y}

        # Loop over queried fields and append under respective related titles

        to_be_related = {}

        for attr in (a for a in dict(item) if a not in layer_fields):
            for table, info in joined_tables.items():
                if attr in info['fields']:
                    fk, pk = info['source'], info['target']
                    to_add = item[attr] if attr == fk else item.pop(attr)

                    to_be_related.setdefault(table, {})[attr] = to_add
                    to_be_related[table].setdefault(pk, item[fk])

        # Track source items by item hash, and append related information under unique source items

        if not to_be_related:
            features.append(feature)
        else:
            for table, info in joined_tables.items():
                fk, pk = info['source'], info['target']
                to_add = to_be_related[table]

                item_hash = item_hash_format.format(id=item['db_id'], fk=fk, val=to_add[pk], table=table)
                if item_hash in already_added:
                    removed = to_be_related.pop(table)
                    related = already_added[item_hash]['related']
                    related.setdefault(table, []).append(removed)
                else:
                    related = feature['related']
                    related[table] = [to_add]
                    already_added[item_hash] = feature

            related['count'] += 1

            if to_be_related:
                features.append(feature)  # Some related fields have not been appended

    return features


def json_date_serializer(obj):
    # Handles date serialization when part of the response object

    if hasattr(obj, 'isoformat'):
        serial = obj.isoformat()
        return serial
    return json.JSONEncoder.default(obj)
