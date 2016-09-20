import csv
import io
import json
import logging
import time
import re

from django.db.utils import DatabaseError
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, View

from tablo.geom_utils import Extent
from tablo.models import FeatureService, FeatureServiceLayer

POINT_REGEX = re.compile('POINT\((.*) (.*)\)')
QUERY_LIMIT = 10000

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
            'maxRecordCount': QUERY_LIMIT,
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
            'maxRecordCount': QUERY_LIMIT,
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

        field_attrs = {'name', 'type', 'relatesTo'}
        data['relatedTables'] = [
            {
                'name': r.related_title,
                'fields': [{
                    # Include only specified field attributes if they are present
                    attr: f[attr] for attr in f if attr in field_attrs and attr in f
                } for f in r.fields]
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
            'count': len(features),
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
    query_limit_default = QUERY_LIMIT

    def handle_request(self, request, **kwargs):
        search_params = {}

        # Capture format type: default anything but csv or json to json
        valid_formats = {'csv', 'json'}
        return_format = kwargs.get('f', 'json').lower()
        return_format = return_format if return_format in valid_formats else 'json'

        # When requesting IDs, ArcGIS sends returnIdsOnly AND returnCountOnly, but expects the IDs response
        return_ids_only = return_format == 'json' and kwargs.get('returnIdsOnly', 'false').lower() == 'true'
        return_count_only = not return_ids_only and kwargs.get('returnCountOnly', 'false').lower() == 'true'

        # Capture query bounding parameters (limit/offset does not apply when returning or filtering by object ids)
        object_ids = kwargs['objectIds'].split(',') if kwargs.get('objectIds') else []
        skip_limit = return_ids_only or bool(object_ids)

        limit = 0 if skip_limit else int(kwargs.get('limit') or self.query_limit_default)
        offset = 0 if skip_limit else int(kwargs.get('offset') or 0)

        if 'where' in kwargs and kwargs['where'] != '':
            search_params['additional_where_clause'] = kwargs.get('where')

        if 'time' in kwargs and kwargs['time'] != '':
            start_time, end_time = kwargs['time'].split(',')
            search_params['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(float(start_time) / 1000))
            search_params['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(float(end_time) / 1000))

        search_params['out_sr'] = kwargs.get('outSR')

        if object_ids:
            search_params['object_ids'] = object_ids

        geometry_type = kwargs.get('geometryType')
        if geometry_type:
            if geometry_type == 'esriGeometryEnvelope':
                search_params['extent'] = Extent(json.loads(kwargs['geometry'])).as_sql_poly()
            elif geometry_type == 'esriGeometryPolygon':
                search_params['extent'] = convert_esri_polygon_to_wkt(json.loads(kwargs['geometry']))
            else:
                return HttpResponseBadRequest(json.dumps({'error': 'Unsupported geometryType'}))

        if not return_ids_only and kwargs.get('outFields'):
            return_fields = kwargs['outFields'].split(',') if kwargs.get('outFields') else []
            search_params['return_fields'] = return_fields

        if not return_ids_only and kwargs.get('orderByFields'):
            order_by_fields = kwargs['orderByFields'].split(',') if kwargs.get('orderByFields') else []
            search_params['order_by_fields'] = order_by_fields

        if return_ids_only:
            search_params['ids_only'] = True
            search_params['return_geometry'] = False
        elif return_count_only:
            search_params['count_only'] = True
        elif kwargs.get('returnGeometry', 'true').lower() == 'false':
            search_params['return_geometry'] = False

        try:
            # Query with limit plus one to determine if the limit excluded any features
            query_response = self.feature_service_layer.perform_query(limit, offset, **search_params)
        except ValidationError as ex:
            # Failed validation of provided fields and incoming SQL are handled here
            return HttpResponseBadRequest(json.dumps({'error': ex.message}))
        except DatabaseError:
            return HttpResponseBadRequest(json.dumps({'error': 'Invalid request'}))

        exceeded_limit = query_response.pop('exceeded_limit')
        query_response = query_response.pop('data')

        if return_count_only:
            data = query_response[0]
        elif return_format == 'csv':
            data = io.StringIO()

            if query_response:
                headers = list(query_response[0].keys())
                has_geometry = 'st_astext' in headers

                if has_geometry:
                    headers.remove('st_astext')
                    headers.append('geometry_x_location')
                    headers.append('geometry_y_location')

                writer = csv.DictWriter(data, fieldnames=headers)
                if offset == 0:
                    writer.writeheader()

                for item in query_response:
                    if has_geometry:
                        x_loc, y_loc = str(item['st_astext']).replace('POINT(', '').replace(')', '').split(' ')
                        item['geometry_x_location'] = x_loc
                        item['geometry_y_location'] = y_loc
                        item.pop('st_astext')
                    writer.writerow(item)
        else:
            data = {
                'count': len(query_response),
                'exceededTransferLimit': exceeded_limit
            }
            if return_ids_only:
                object_id_field = self.feature_service_layer.object_id_field
                data['objectIdFieldName'] = object_id_field
                data['objectIds'] = [feature[object_id_field] for feature in query_response]
            else:
                queried = set(query_response[0].keys()) if query_response else set()
                features = convert_wkt_to_esri_feature(query_response, self.feature_service_layer)
                data.update({
                    'count': len(features),
                    'fields': self.feature_service_layer.fields,
                    'geometryType': 'esriGeometryPoint',
                    'features': features
                })

                if object_ids and any('.' in field for field in queried):
                    data['relatedFields'] = {
                        r.related_title: r.fields for r in self.feature_service_layer.relations
                    }

        if return_format == 'csv':
            content = data.getvalue()
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


def convert_esri_polygon_to_wkt(polygon_json):
    polygon_string = 'MULTIPOLYGON(('
    for ring in polygon_json['rings']:
        polygon_string += '('
        for item in ring:
            polygon_string += '{0} {1},'.format(str(item[0]), str(item[1]))
        polygon_string = polygon_string[:-1]
        polygon_string += '),'
    polygon_string = polygon_string[:-1]
    polygon_string += '))'
    return polygon_string


def convert_wkt_to_esri_feature(response_items, for_layer):

    if not response_items:
        return []

    # Gather related table information to ensure fields are correctly represented

    query_fields = {f for f in response_items[0]}
    has_geometry = 'st_astext' in query_fields

    layer_fields = {f['name'] for f in for_layer.fields if f['name'] in query_fields}
    layer_fields.add('id')  # Ensures related items are placed correctly even when fk appears more than once in source

    joined_tables = {
        r.related_title: {
            'source': r.source_column,
            'target': r.target_column,
            'fields': {f['name'] for f in r.fields if f['qualified'] in query_fields}
        } for r in for_layer.relations
    }
    joined_tables = {k: v for k, v in joined_tables.items() if v['fields']}

    # Loop over queried items and construct feature response

    item_hash_format = 'id:{id}.{fk}:{val}.{table}'
    already_added = {}
    features = []

    for item in response_items:
        item['related'] = {}
        feature = {'attributes': item}

        if has_geometry:
            # This only currently works for points

            point_text = item.pop('st_astext')
            match = POINT_REGEX.match(point_text)
            if not match:
                raise ValueError('Invalid Point Geometry: {0}'.format(point_text))

            x, y = (float(x) for x in match.groups())
            feature['geometry'] = {'x': x, 'y': y}

        # Loop over queried fields and append under respective related titles

        to_be_related = {}

        for attr in (a for a in dict(item) if a not in layer_fields and '.' in a):
            related_title, attr_name = attr.split('.')
            table = joined_tables[related_title]

            if attr_name in table['fields']:
                fk, pk = table['source'], table['target']
                to_add = item[attr] if attr == fk else item.pop(attr)

                to_be_related.setdefault(related_title, {})[attr_name] = to_add
                to_be_related[related_title].setdefault(pk, item[fk])

        if not to_be_related:
            # Prevent duplicate source items when related items were in the join but not selected
            item.pop('related', None)

            # Time queries will not have object_id_field, but can just include all features
            if for_layer.object_id_field in item:
                item_hash = item[for_layer.object_id_field]
                if item_hash not in already_added:
                    already_added[item_hash] = feature
                    features.append(feature)
            else:
                features.append(feature)
        else:
            # Append unique source items by item hash, and append related information under each

            for table, info in joined_tables.items():
                fk, pk = info['source'], info['target']
                to_add = to_be_related[table]

                item_hash = item_hash_format.format(id=item['db_id'], fk=fk, val=to_add[pk], table=table)
                if item_hash in already_added:
                    removed = to_be_related.pop(table)
                    related = already_added[item_hash]['attributes']['related']
                    related.setdefault(table, []).append(removed)
                else:
                    related = feature['attributes']['related']
                    related[table] = [to_add]
                    already_added[item_hash] = feature

            if to_be_related:
                features.append(feature)  # Some related fields have not been appended

    return features


def json_date_serializer(obj):
    # Handles date serialization when part of the response object

    if hasattr(obj, 'isoformat'):
        serial = obj.isoformat()
        return serial
    return json.JSONEncoder.default(obj)
