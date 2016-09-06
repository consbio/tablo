# Tablo

## What is it?

Tablo is a lightweight Django application that creates a interface layer for interacting with spatial data
stored within a PostGIS database.

## How do I set it up?

To keep things separate, you will most likely want to work within a python virtual environment. This just makes
things easier to manage in general. A good tool for managing virtual environments can be found at
https://virtualenvwrapper.readthedocs.io/en/latest/.

Tablo has been written to support Python 3.5, so you will need to make sure your virtual environment is using
Python 3.5.

### Dependencies

Tablo is a Django application that relies on a PostGIS database. So, the first two things you'll need to work with
Tablo are:

1. A PostGIS database (version 9.4 or above)
2. A Django Project

#### Setting up a PostGIS database

The scope of this document is not large enough to encapsulate all that is required in installing a PostGIS database.
See http://postgis.net/install/ for information on how to install it on your own system (or on a remote server).

#### Setting up a Django Project

See https://docs.djangoproject.com/en/1.8/intro/tutorial01/#creating-a-project for instructions on how to set up
a Django project. Tablo was tested using Django version 1.8.6.

For example, you could create a project called tablo_project by issuing the command:
`django-admin startproject tablo_project`

Anywhere in this documentation where it refers to the Django project, it will be referenced as tablo_project.

#### Other Dependencies

Tablo relies on a few libraries that can often be more difficult to install. These include:

* pyproj (https://github.com/jswhit/pyproj)
* lxml (via messytables) (http://lxml.de/)
* GDAL (https://pypi.python.org/pypi/GDAL/)

See these websites to install these libraries first, as they may depend on other executables existing in your
environment.

### Installing Tablo

There are two main ways to install tablo; directly, or indirectly from a cloned repository.

To install directly, use the standard pip installation:

`pip install git+https://github.com/consbio/tablo.git`

To install indirectly from a cloned repository:

1. Clone this repository
2. Install the app using pip and pointing to your local repository, but use the `--editable` flag, as in:
`pip install --editable c:\tablo`

### Modify Django Settings

In your tablo_project/tablo_project settings file, make the following modifications:

```
INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    ...
    'tastypie',
    'tablo'
)
```

```
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': '{ database name }',
        'HOST': '{ database host }',
        'USER': '{ database user }',
        'PASSWORD': '{ database password}'
    }
}
```

### Modify urls.py

In tablo_project/tablo_project/urls.py, make sure that the tablo.urls are included:

```
urlpatterns = [
    url(r'^', include('tablo.urls')),
    url(r'^admin/', include(admin.site.urls)),
]
```

### Add API Key Authentication

To allow other applications to use Tablo using an API key rather than a full user login, add middleware.py file that
looks like this:

```
from tastypie.authentication import ApiKeyAuthentication


class TastypieApiKeyMiddleware(object):
    """Middleware to authenticate users using API keys for regular Django views"""

    def process_request(self, request):
        ApiKeyAuthentication().is_authenticated(request)
```

Then add an additional INSTALLEDAPP referencing `tablo_project.middleware.TastypieApiKeyMiddleware`.

### Create a tablo user

`python manage.py createsuperuser --username=tablo --email=your.email@somewhere.com`

Supply a password for the tablo user.

### Run the server

Make sure that your path to osgeo is in your PATH variable.

Run the server by issuing the `manage.py runserver` command.

### Setup the API Key

Go to http://localhost/admin and login as tablo, using the password you supplied above.

Add an API key for the tablo user. This is the API key you will want to set for any applications that communicate
with the tablo server.
