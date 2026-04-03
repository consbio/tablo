DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'tablo',
        'HOST': 'localhost',
        'USER': 'tablo',
        'PASSWORD': 'tablo'
    }
}
USE_TZ = False
SITE_ID = 1

STATIC_URL = '/static/'
SECRET_KEY = 'NOT_SO_SECRET'

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'tastypie',
    'tablo',
)

MIDDLEWARE = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'tablo.tests.middleware.TastypieApiKeyMiddleware'
)

ROOT_URLCONF = 'tablo.urls'

