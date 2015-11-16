import logging

from django.conf.urls import url
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.http import Http404
from tastypie import fields
from tastypie.authentication import MultiAuthentication, SessionAuthentication, ApiKeyAuthentication
from tastypie.authorization import DjangoAuthorization, Authorization
from tastypie.constants import ALL
from tastypie.http import HttpMultipleChoices
from tastypie.resources import ModelResource
from tastypie.serializers import Serializer

from tablo.models import FeatureService, FeatureServiceLayer


logger = logging.getLogger(__name__)


class FeatureServiceResource(ModelResource):

    layers = fields.ToManyField('tablo.api.FeatureServiceLayerResource', attribute='featureservicelayer_set',
        full=True, full_list=False, related_name='service')

    class Meta:
        object_class = FeatureService
        resource_name = 'featureservice'
        list_allowed_methods = ['get', 'post', 'delete']
        detail_allowed_methods = ['get', 'post', 'put', 'patch', 'delete']
        serializer = Serializer(formats=['json', 'jsonp'])
        queryset = FeatureService.objects.all()
        authorization = Authorization()
        #authentication = MultiAuthentication(SessionAuthentication(), ApiKeyAuthentication())
        #authorization = DjangoAuthorization

    def prepend_urls(self):
        return [
            url(
                r'^(?P<resource_name>{0})/(?P<service_id>[\w\-@\._]+)/finalize'.format(
                    self._meta.resource_name
                ), self.wrap_view('finalize'), name="api_featureservice_finalize"
            )
        ]

    def finalize(self, request, **kwargs):
        print(kwargs['service_id'])
        try:
            service = FeatureService.objects.get(id=kwargs['service_id'])
        except ObjectDoesNotExist:
            return Http404()

        service.finalize(service.dataset_id)

        return self.create_response(request, {'status': 'good'})


class FeatureServiceLayerResource(ModelResource):

    service = fields.ToOneField(FeatureServiceResource, attribute='service', full=False)

    class Meta:
        object_class = FeatureServiceLayer
        resource_name = 'featureservicelayer'
        filtering = {'layer_order': ALL}
        list_allowed_methods = ['get', 'post', 'delete']
        detail_allowed_methods = ['get', 'post', 'put', 'patch', 'delete']
        serializer = Serializer(formats=['json', 'jsonp'])
        queryset = FeatureServiceLayer.objects.all()
        authorization = Authorization()
        #authentication = MultiAuthentication(SessionAuthentication(), ApiKeyAuthentication())
        #authorization = DjangoAuthorization




