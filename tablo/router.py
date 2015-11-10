
class FeatureServiceRouter(object):
    '''
    The FeatureServiceRouter is a Django router that determines which models will be handled by the
    'feature_services' database.
    https://docs.djangoproject.com/en/1.8/topics/db/multi-db/#topics-db-multi-db-routing
    '''

    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'feature_services':
            return 'feature-services'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'feature_services':
            return 'feature-services'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label == 'feature_services' and obj2._meta.app_label == 'feature_services':
            return True
        return None

    # The signature for this will change in Django 1.8.
    def allow_migrate(self, db, model):
        if db == 'feature-services':
            return model and model._meta.app_label == 'feature_services'
        elif model and model._meta.app_label == 'feature_services':
            return False
        return True

