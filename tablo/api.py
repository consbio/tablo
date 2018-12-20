import json
import logging
import re

from django.conf.urls import url
from django.core.exceptions import ObjectDoesNotExist
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

from tablo.csv_utils import determine_optional_fields, determine_x_and_y_fields, prepare_csv_rows
from tablo.exceptions import derive_error_response_data, InvalidFileError
from tablo.models import Column, FeatureService, FeatureServiceLayer, FeatureServiceLayerRelations, TemporaryFile
from tablo.models import add_geometry_column, add_or_update_database_fields
from tablo.models import copy_data_table_for_import, create_aggregate_database_table, create_database_table
from tablo.models import populate_aggregate_table, populate_data, populate_point_data

logger = logging.getLogger(__name__)

TYPE_REGEX = re.compile(r'\([^\)]*\)')


class FeatureServiceResource(ModelResource):
    """
    The FeatureService resource, located at ``{tablo_server}/api/v1/featureservice``, allows you to create, edit
    and delete feature services within Tablo.

    Once your data has been deployed through the deploy endpoint, you can create a feature service by sending a POST
    message to the above endpoint with data structured as:

    .. code-block:: json

        {
            "description": "",
            "copyright_text": "",
            "spatial_reference": "{'wkid': 3857}",
            "units": "esriMeters",
            "allow_geometry_updates": false,
            "layers": [
                {
                    "layer_order": 0,
                    "table": "db_dataset_id_import",
                    "name": "layername",
                    "description": null,
                    "geometry_type": "esriGeometryPoint",
                    "supports_time": false,
                    "start_time_field": null,
                    "time_interval": 0,
                    "time_interval_units": null,
                    "drawing_info": {
                        "renderer": {
                            "description": "",
                            "label": "",
                            "symbol": {
                                "angle": 0,
                                "color": [255, 0, 0, 255],
                                "size": 5,
                                "style": "esriSMSCircle",
                                "type": "esriSMS",
                                "xoffset": 0,
                                "yoffset": 0
                            },
                            "type": "simple"
                        }
                    }
                }
            ]
        }

    `drawing_info` contains ESRI styling for the FeatureService geometry type.
    The creation will return a URL that will contain the Service ID of your newly created feature service.


    """

    layers = fields.ToManyField(
        'tablo.api.FeatureServiceLayerResource',
        attribute='featureservicelayer_set',
        related_name='service',
        full=True,
        full_list=False
    )

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
                r'^(?P<resource_name>{0})/(?P<service_id>[\w\-@\._]+)/combine-tables'.format(
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
        """
        The finalize endpoint, located at ``{tablo_host}/api/v1/featureservice/{service_id}/finalize``.
        It allows you to finalize the feature service and mark it as available for use.
        This endpoint moves the data from the temporary database table and into its permanent one.
        It is accessed with a **service_id** parameter specifying the ID of the service you want to finalize.
        """

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
        row_columns = [Column(column=col['name'], type=col['type'], required=col['required']) for col in columns]
        dataset_list = json.loads(request.POST.get('dataset_list'))
        table_name = create_aggregate_database_table(row_columns, service.dataset_id)

        add_geometry_column(service.dataset_id)
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
                logger.exception(e)
                add_response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error adding feature: {}'.format(e)
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
                logger.exception(e)
                update_response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error updating feature: {}'.format(e)
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
                logger.exception(e)
                delete_response_obj.append({
                    'success': False,
                    'error': {
                        'code': -999999,
                        'description': 'Error deleting feature: {}'.format(e)
                    }
                })

        response_obj = {
            'addResults': add_response_obj,
            'updateResults': update_response_obj,
            'deleteResults': delete_response_obj
        }

        if original_time_extent:
            new_time_extent = feature_service_layer.get_raw_time_extent()
            has_new_time_extent = (
                new_time_extent[0] != original_time_extent[0] or
                new_time_extent[1] != original_time_extent[1]
            )
            if has_new_time_extent:
                response_obj['new_time_extent'] = json.dumps(new_time_extent)

        return self.create_response(request, response_obj)


class FeatureServiceLayerRelationsResource(ModelResource):

    layer_id = fields.IntegerField(attribute='layer_id', readonly=True)
    field_defs = fields.ListField(attribute='fields', readonly=True)

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
    field_defs = fields.ListField(attribute='fields', readonly=True)
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
        detail_uri_name = 'id'
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
        """
        Describe, located at the ``{tablo-server}/api/v1/temporary-files/{uuid}/describe`` endpoint, will describe
        the uploaded CSV file. This allows you to know the column names and data types that were found within the
        file.

        :return:
            A JSON object in the following format:

            .. code-block:: json

                {
                    "fieldNames": ["field one", "field two", "latitude", "longitude"],
                    "dataTypes": ["String", "Integer", "Double", "Double"],
                    "optionalFields": ["field one"],
                    "xColumn": "longitude",
                    "yColumn": "latitude",
                    "filename": "uploaded.csv"
                }

            **fieldNames**
                A list of field (column) names within the CSV

            **dataTypes**
                A list of data types for each of the columns. The index of this list will match the index of the
                fieldNames list.

            **optionalFields**
                A list of fields that had empty values, and are taken to be optional.

            **xColumn**
                The best guess at which column contains X spatial coordinates.

            **yColumn**
                The best guess at which column contains Y spatial coordinates.

            **filename**
                The name of the file being described

        """
        self.is_authenticated(request)

        bundle = self.build_bundle(request=request)
        obj = self.obj_get(bundle, **self.remove_api_resource_names(kwargs))

        if obj.extension == 'csv':
            csv_file_name = obj.file.name
        else:
            error_json = derive_error_response_data(InvalidFileError(
                underlying='Unsupported file format', extension=obj.extension
            ))
            raise ImmediateHttpResponse(HttpBadRequest(
                content=json.dumps(error_json),
                content_type='application/json'
            ))

        try:
            row_set = prepare_csv_rows(obj.file)
            sample_row = next(row_set.sample)
        except StopIteration as e:
            error_json = derive_error_response_data(InvalidFileError(
                underlying=e, lines=0
            ))
            raise ImmediateHttpResponse(HttpBadRequest(
                content=json.dumps(error_json),
                content_type='application/json'
            ))

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
        """
            The deploy endpoint, at ``{tablo_server}/api/v1/temporary-files/{uuid}/{dataset_id}/deploy/`` deploys
            the file specified by {uuid} into a database table named after the {dataset_id}. The {dataset_id} must
            be unique for the instance of Tablo.

            With the deploy endpoint, this is the start of what Tablo considers an import. The data will be
            temporarily stored in an import table until the finalize endpoint for the dataset_id is called.

            POST messages to the deploy endpoint should include the following data:

            **csv_info**
                Information about the CSV file. This is generally that information obtained through the
                describe endpoint, but can be modified to send additional information or modify it.
            **fields**
                A list of field JSON objects in the following format:

                .. code-block:: json

                    {
                        "name": "field_name",
                        "type": "text",
                        "value": "optional value",
                        "required": true
                    }

                The value can be specified if the field is a constant value throughout the table. This can
                be use for adding audit information.

            :return:
                An empty HTTP 200 response if the deploy was successful. An error response if otherwise.
        """
        self.is_authenticated(request)

        try:
            dataset_id = kwargs.pop('dataset_id', None)

            bundle = self.build_bundle(request=request)
            obj = self.obj_get(bundle, **self.remove_api_resource_names(kwargs))

            csv_info = json.loads(request.POST.get('csv_info'))
            additional_fields = json.loads(request.POST.get('fields'))

            # Use separate iterator of table rows to not exaust the main one
            optional_fields = determine_optional_fields(prepare_csv_rows(obj.file))

            row_set = prepare_csv_rows(obj.file, csv_info)
            sample_row = next(row_set.sample)
            table_name = create_database_table(sample_row, dataset_id, optional_fields=optional_fields)
            bundle.data['table_name'] = table_name

            populate_data(table_name, row_set)
            add_or_update_database_fields(table_name, additional_fields)
            add_geometry_column(dataset_id)
            populate_point_data(dataset_id, csv_info)

            obj.delete()  # Temporary file has been moved to database, safe to delete

        except Exception as e:
            logger.exception(e)

            # Likely coming from uploaded data sent to populate_data
            raise ImmediateHttpResponse(HttpBadRequest(
                content=json.dumps(derive_error_response_data(e)),
                content_type='application/json'
            ))

        return self.create_response(request, bundle)

    def append(self, request, **kwargs):
        self.is_authenticated(request)

        try:
            dataset_id = kwargs.pop('dataset_id', None)

            bundle = self.build_bundle(request=request)
            obj = self.obj_get(bundle, **self.remove_api_resource_names(kwargs))

            csv_info = json.loads(request.POST.get('csv_info'))
            additional_fields = json.loads(request.POST.get('fields'))

            row_set = prepare_csv_rows(obj.file)
            sample_row = next(row_set.sample)
            table_name = create_database_table(sample_row, dataset_id, append=True)
            bundle.data['table_name'] = table_name

            add_or_update_database_fields(table_name, additional_fields)
            populate_data(table_name, row_set)
            populate_point_data(dataset_id, csv_info)

            obj.delete()  # Temporary file has been moved to database, safe to delete

        except Exception as e:
            logger.exception(e)

            # Likely coming from uploaded data sent to populate_data
            raise ImmediateHttpResponse(HttpBadRequest(
                content=json.dumps(derive_error_response_data(e)),
                content_type='application/json'
            ))

        return self.create_response(request, bundle)
