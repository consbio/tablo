import json

import requests

SERVICE_URL = 'http://puffin.corvallis.consbio.org:8383/tablo/arcgis/rest/services/555/FeatureServer/0'
TEST_ADD_FEATURE = [
    {
        'geometry': {'x': -122.26, 'y': 45.47},
        'attributes': {
            'entry_id': 6,
            'team_name': 'bob',
            'name_of_the_stream': 'streamy',
            'longitude': -122.26,
            'latitude': 45.47,
            'temperature_reading': 70,
            'created_by': 'mike test'
        }
    }
]

TEST_UPDATE_FEATURE = [
    {
        'geometry': {'x': -122.00, 'y': 45.37},
        'attributes': {
            'db_id': 0,
            'team_name': 'bob',
            'created_by': 'mike live'
        }
    }
]


def run_test():
    rollback_on_failure = False
    arguments = {
        'f': 'json',
        'features': json.dumps(TEST_ADD_FEATURE),
        'rollbackOnFailure': rollback_on_failure
    }

    response = requests.post(SERVICE_URL + '/addFeatures', data=arguments)
    response_object = response.json()
    assert 'addResults' in response_object

    added_features = response_object['addResults']
    assert len(added_features) == len(TEST_ADD_FEATURE)

    first_added_feature = added_features[0]

    assert 'success' in first_added_feature
    assert first_added_feature['success']

    assert 'objectId' in first_added_feature
    object_id = first_added_feature['objectId']
    assert object_id > 0

    TEST_UPDATE_FEATURE[0]['attributes']['db_id'] = object_id

    update_arguments = {
        'f': 'json',
        'features': json.dumps(TEST_UPDATE_FEATURE),
        'rollbackOnFailure': rollback_on_failure
    }

    update_response = requests.post(SERVICE_URL + '/updateFeatures', data=update_arguments)
    update_response_obj = update_response.json()

    assert 'editResults' in update_response_obj

    updated_features = update_response_obj['editResults']
    assert len(added_features) == len(TEST_UPDATE_FEATURE)

    first_updated_feature = updated_features[0]

    assert 'success' in first_updated_feature
    assert first_updated_feature['success']

    assert 'objectId' in first_updated_feature
    object_id = first_updated_feature['objectId']
    assert object_id > 0

    delete_arguments = {
        'f': 'json',
        'objectIds': object_id
    }

    delete_response = requests.post(SERVICE_URL + '/deleteFeatures', data=delete_arguments)
    delete_response_obj = delete_response.json()
    print(delete_response_obj)


if __name__ == '__main__':
    run_test()