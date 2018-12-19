from django.utils.deconstruct import deconstructible
from django.utils.functional import LazyObject
from storages.backends.s3boto3 import S3Boto3Storage


@deconstructible
class SerializableS3Boto3Storage(S3Boto3Storage):
    pass


class DefaultPublicStorage(LazyObject):
    def _setup(self):
        self._wrapped = SerializableS3Boto3Storage(acl="public-read", querystring_auth=False, secure_urls=False)


default_public_storage = DefaultPublicStorage()


def delete_directory(storage, directory):
    """ Recursively deletes all files under the given directory """

    if not directory or directory == '/':
        raise Exception('Will not delete root directory!')

    dirs, files = storage.listdir(directory)
    for storage_file in files:
        storage.delete('/'.join((directory, storage_file)))
    for storage_dir in dirs:
        delete_directory(storage, '/'.join((directory, storage_dir)))
