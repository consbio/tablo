import os
import sys

import django
from django.conf import settings
from django.test.utils import get_runner

os.environ['DJANGO_SETTINGS_MODULE'] = 'tablo.tests.settings'
django.setup()
test_dir = os.path.dirname(__file__)
sys.path.insert(0, test_dir)


def runtests():
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests([])
    sys.exit(bool(failures))


if __name__ == '__main__':
    runtests()
