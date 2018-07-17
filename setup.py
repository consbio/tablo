from setuptools import setup

setup(
    name='tablo',
    description='A PostGIS table to feature service app for Django',
    keywords='feature service, map server, postgis, django',
    version='1.1.2',
    packages=['tablo', 'tablo.migrations', 'tablo.interfaces', 'tablo.interfaces.arcgis'],
    install_requires=[
        'Django>=1.8.0,<1.12.0', 'sqlparse>=0.1.18', 'pyproj', 'six', 'messytables',
        'django-tastypie==0.14.*', 'psycopg2', 'Pillow>=2.9.0', 'django-storages>=1.5.2', 'boto3>=1.4.4'
    ],
    test_suite='tablo.tests.runtests.runtests',
    tests_require=['django-nose', 'rednose'],
    url='http://github.com/consbio/tablo',
    license='BSD',
)
