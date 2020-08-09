from setuptools import setup

setup(
    name='tablo',
    description='A PostGIS table to feature service app for Django',
    keywords='feature service, map server, postgis, django',
    version='2.0',
    packages=['tablo', 'tablo.migrations', 'tablo.interfaces', 'tablo.interfaces.arcgis'],
    install_requires=[
        'Django==2.2.*', 'sqlparse>=0.3.1', 'pyproj', 'pandas==1.0.*',
        'django-tastypie==0.14.*', 'psycopg2-binary', 'Pillow>=7.1.2', 'django-storages==1.9.*',
        'boto3==1.14.*', 'sqlalchemy==1.3.*', 'geoalchemy2==0.7.*'
    ],
    test_suite='tablo.tests.runtests.runtests',
    tests_require=['django-nose', 'rednose'],
    url='http://github.com/consbio/tablo',
    license='BSD',
)
