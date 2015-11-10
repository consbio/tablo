from setuptools import setup

setup(
    name='tablo',
    description='A PostGIS table to feature service app for Django',
    keywords='feature service, map server, postgis, django',
    version='0.1.0',
    packages=['tablo'],
    install_requires=['Django>=1.7.0'],
    url='http://github.com/consbio/tablo',
    license='BSD',
)