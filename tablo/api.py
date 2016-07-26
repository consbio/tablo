import json
import logging
import re

from django.conf.urls import url
from django.core.exceptions import ObjectDoesNotExist
from django.db import InternalError
from django.http import Http404
from tastypie import fields
from tastypie.authentication import MultiAuthentication, SessionAuthentication, ApiKeyAuthentication
from tastypie.authorization import DjangoAuthorization
from tastypie.constants import ALL
from tastypie.exceptions import ImmediateHttpResponse
from tastypie.http import HttpBadRequest
from tastypie.resources import ModelResource
from tastypie.serializers import Serializer
from tastypie.utils import trailing_slash

from tablo.csv_utils import determine_x_and_y_fields, prepare_csv_rows
from tablo.models import Column, FeatureService, FeatureServiceLayer, FeatureServiceLayerRelations, TemporaryFile
from tablo.models import add_point_column, add_or_update_database_fields
from tablo.models import copy_data_table_for_import, create_aggregate_database_table, create_database_table
from tablo.models import populate_aggregate_table, populate_data, populate_point_data

logger = logging.getLogger(__name__)

TYPE_REGEX = re.compile(r'\([^\)]*\)')


class FeatureServiceResource(ModelResource):

    layers = fields.ToManyField('tablo.api.FeatureServiceLayerResource', attribute='featureservicelayer_set',
        full=True, full_list=False, related_name='service')

    class Meta:
        object_class = FeatureService
        resource_name = 'featureservice'
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get', 'post', 'put', 'patch', 'delete']
        serializer = Serializer(formats=['json', 'jsonp'])
        queryset = FeatureService.objects.all()
        authentication = MultiAuthentication(SessionAuthentication(), ApiKeyAuthentication())
        authorization = DjangoAuthorization()

    def prepend_urls(self):
        return [
            url(
                r'^(?P<resource_name>{0})/(?P<service_id>[\w\-@\._]+)/finalize'.format(
                    self._meta.resource_name
                ), self.wrap_view('finalize'), name="api_featureservice_finalize"
            ),
            url(
                r'^(?P<resource_name>{0})/(?P<service_id>[\w\-@\._]+)/copy'.format(
                    self._meta.resource_name
                ), self.wrap_view('copy'), name="api_featureservice_copy"
            ),
            url(
                r'^(?P<resource_name>{0})/(?P<service_id>[\w\-@\._]+)/combine_tables'.format(
                    self._meta.resource_name
                ), self.wrap_view('combine_tables'), name="api_featureservice_combine_tables"
            ),
            url(
                r'^(?P<resource_name>{0})/(?P<service_id>[\w\-@\._]+)/apply-edits'.format(
                    self._meta.resource_name
                ), self.wrap_view('apply_edits'), name="api_featureservice_apply_edits"
            )
        ]

    def finalize(self, request, **kwargs):
        try:
            service = FeatureService.objects.get(id=kwargs['service_id'])
        except ObjectDoesNotExist:
            return Http404()

        service.finalize(service.dataset_id)

        return self.create_response(request, {'status': 'good'})

    def copy(self, request, **kwargs):
        try:
            service = FeatureService.objects.get(id=kwargs['service_id'])
        except ObjectDoesNotExist:
            return Http404()

        table_name = copy_data_table_for_import(service.dataset_id)

        old_layers = service.featureservicelayer_set.all()

        service.id = None
        service._initial_extent = None
        service._full_extent = None

        service.save()

        for layer in old_layers:
            layer.id = None
            layer.service = service
            layer._extent = None
            layer._time_extent = None
            layer.table = table_name
            layer.save()

        return self.create_response(request, {
            'service_id': service.id,
            'time_extent': layer.time_extent
        })

    def combine_tables(self, request, **kwargs):
        try:
            service = FeatureService.objects.get(id=kwargs['service_id'])
        except ObjectDoesNotExist:
            return Http404()

        columns = json.loads(request.POST.get('columns'))
        row_columns = [Column(column=column['name'], type=column['type']) for column in columns]

        dataset_list = json.loads(request.POST.get('dataset_list'))
        table_name = create_aggregate_database_table(row_columns, service.dataset_id)
        add_point_column(service.dataset_id)
        populate_aggregate_table(table_name, row_columns, dataset_list)
        service._full_extent = None
        service._initial_extent = None
        service.featureservicelayer_set.first()._extent = None
        service.save()

        return self.create_response(request, {'table_name': table_name})

    def apply_edits(self, request, **kwargs):

        try:
            service = FeatureService.objects.get(id=kwargs['service_id'])
        except ObjectDoesNotExist:
            return Http404()

        adds = json.loads(request.POST.get('adds', '[]'))
        updates = json.loads(request.POST.get('updates', '[]'))
        delete_list = request.POST.get('deletes', None)
        deletes = str(delete_list).split(',') if delete_list else []

        add_response_obj = []
        feature_service_layer = service.featureservicelayer_set.first()
        original_time_extent = (
            feature_service_layer.get_raw_time_extent() if feature_service_layer.supports_time else None
        )
        for feature in adds:
            try:
                object_id = feature_service_layer.add_feature(feature)
                add_response_obj.append({
                    'objectId': object_id,
                    'success': True
                })
            except Exception as e:
                logger.exception()
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
                object_id = feature_service_layer.update_feature(feature)
                update_response_obj.append({
                    'objectId': object_id,
                    'success': True
                })
            except Exception as e:
                logger.exception()
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
                object_id = feature_service_layer.delete_feature(object_id)
                delete_response_obj.append({
                    'objectId': object_id,
                    'success': True
                })
            except Exception as e:
                logger.exception()
                delete_response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error deleting feature: ' + str(e)
                    }
                })

        response_obj = {
            'addResults': add_response_obj,
            'updateResults': update_response_obj,
            'deleteResults': delete_response_obj
        }

        if original_time_extent:
            new_time_extent = feature_service_layer.get_raw_time_extent()
            if (
                new_time_extent[0] != original_time_extent[0] or
                new_time_extent[1] != original_time_extent[1]
            ):
                response_obj['new_time_extent'] = json.dumps(new_time_extent)

        return self.create_response(request, response_obj)


class FeatureServiceLayerRelationsResource(ModelResource):

    layer_id = fields.IntegerField(attribute='layer_id', readonly=True)

    class Meta:
        object_class = FeatureServiceLayerRelations
        resource_name = 'featureservicelayerrelations'
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        serializer = Serializer(formats=['json', 'jsonp'])
        queryset = FeatureServiceLayerRelations.objects.select_related('layer').all()
        authentication = MultiAuthentication(SessionAuthentication(), ApiKeyAuthentication())
        authorization = DjangoAuthorization()


class FeatureServiceLayerResource(ModelResource):

    service = fields.ToOneField(FeatureServiceResource, attribute='service', full=False)
    relations = fields.ToManyField(
        FeatureServiceLayerRelationsResource,
        attribute='featureservicelayerrelations_set', full=True, readonly=True, null=True
    )

    class Meta:
        object_class = FeatureServiceLayer
        resource_name = 'featureservicelayer'
        filtering = {'layer_order': ALL, 'table': ALL}
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get', 'post', 'put', 'patch', 'delete']
        serializer = Serializer(formats=['json', 'jsonp'])
        queryset = FeatureServiceLayer.objects.all()
        authentication = MultiAuthentication(SessionAuthentication(), ApiKeyAuthentication())
        authorization = DjangoAuthorization()


class TemporaryFileResource(ModelResource):
    uuid = fields.CharField(attribute='uuid', readonly=True)

    class Meta:
        queryset = TemporaryFile.objects.all()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get', 'delete']
        resource_name = 'temporary-files'
        authentication = MultiAuthentication(SessionAuthentication(), ApiKeyAuthentication())
        authorization = DjangoAuthorization()
        fields = ['uuid', 'date', 'filename']
        detail_uri_name = 'uuid'
        serializer = Serializer(formats=['json', 'jsonp'])

    def _convert_number(self, number):
        """Converts a number to float or int as appropriate"""

        number = float(number)
        return int(number) if number.is_integer() else float(number)

    def prepend_urls(self):
        return [
            url(
                r"^(?P<resource_name>%s)/(?P<%s>.*?)/describe%s$" % (
                    self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()
                ),
                self.wrap_view('describe'), name='temporary_file_describe'
            ),
            url(
                r"^(?P<resource_name>%s)/(?P<%s>.*?)/(?P<dataset_id>[\w\-@\._]+)/deploy%s$" % (
                    self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()
                ),
                self.wrap_view('deploy'), name='temporary_file_deploy'
            ),
            url(
                r"^(?P<resource_name>%s)/(?P<%s>.*?)/(?P<dataset_id>[\w\-@\._]+)/append%s$" % (
                    self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()
                ),
                self.wrap_view('append'), name='temporary_file_append'
            )
        ]

    def describe(self, request, **kwargs):
        self.is_authenticated(request)

        bundle = self.build_bundle(request=request)
        obj = self.obj_get(bundle, **self.remove_api_resource_names(kwargs))

        if obj.extension == 'csv':
            csv_file_name = obj.file.name
        else:
            raise ImmediateHttpResponse(HttpBadRequest('Unsupported file format.'))

        row_set = prepare_csv_rows(obj.file)

        sample_row = next(row_set.sample)
        bundle.data['fieldNames'] = [cell.column for cell in sample_row]
        bundle.data['dataTypes'] = [TYPE_REGEX.sub('', str(cell.type)) for cell in sample_row]
        bundle.data['optionalFields'] = determine_optional_fields(row_set)

        x_field, y_field = determine_x_and_y_fields(sample_row)
        if x_field and y_field:
            bundle.data['xColumn'] = x_field
            bundle.data['yColumn'] = y_field

        bundle.data.update({'file_name': csv_file_name})

        return self.create_response(request, bundle)

    def deploy(self, request, **kwargs):
        self.is_authenticated(request)

        try:
            dataset_id = kwargs.get('dataset_id')

            del kwargs['dataset_id']
            bundle = self.build_bundle(request=request)
            obj = self.obj_get(bundle, **self.remove_api_resource_names(kwargs))

            csv_info = json.loads(request.POST.get('csv_info'))
            additional_fields = json.loads(request.POST.get('fields'))

            # Use separate iterator of table rows to not exaust the main one
            optional_fields = determine_optional_fields(prepare_csv_rows(obj.file))

            row_set = prepare_csv_rows(obj.file)
            sample_row = next(row_set.sample)
            table_name = create_database_table(sample_row, dataset_id, optional_fields=optional_fields)
            populate_data(table_name, row_set)

            add_or_update_database_fields(table_name, additional_fields)

            bundle.data['table_name'] = table_name

            add_point_column(dataset_id)

            populate_point_data(dataset_id, csv_info)
            obj.delete()    # Temporary file has been moved to database, safe to delete
        except InternalError:
            logger.exception()
            raise ImmediateHttpResponse(HttpBadRequest('Error deploying file to database.'))

        return self.create_response(request, bundle)

    def append(self, request, **kwargs):
        self.is_authenticated(request)

        try:
            dataset_id = kwargs.get('dataset_id')

            del kwargs['dataset_id']
            bundle = self.build_bundle(request=request)
            obj = self.obj_get(bundle, **self.remove_api_resource_names(kwargs))

            csv_info = json.loads(request.POST.get('csv_info'))
            additional_fields = json.loads(request.POST.get('fields'))

            row_set = prepare_csv_rows(obj.file)
            sample_row = next(row_set.sample)
            table_name = create_database_table(sample_row, dataset_id, append=True)

            add_or_update_database_fields(table_name, additional_fields)
            populate_data(table_name, row_set)

            bundle.data['table_name'] = table_name

            populate_point_data(dataset_id, csv_info)
            obj.delete()    # Temporary file has been moved to database, safe to delete
        except InternalError:
            logger.exception()
            raise ImmediateHttpResponse(HttpBadRequest('Error deploying file to database.'))

        return self.create_response(request, bundle)


def json_date_serializer(obj):
    # Handles date serialization when part of the response object

    if hasattr(obj, 'isoformat'):
        serial = obj.isoformat()
        return serial
    return json.JSONEncoder.default(obj)


def determine_optional_fields(row_set):

    optional_fields = set([])
    for row in row_set:
        for cell in row:
            if cell.empty:
                optional_fields.add(cell.column)
    return optional_fields
