# python setup.py test
#   or
# python runtests.py [anymail.tests.test_x anymail.tests.test_y.SomeTestCase ...]

import sys

from django import setup
from django.conf import settings
from django.test.runner import DiscoverRunner as TestRunner


APP = 'anymail'

settings.configure(
    DEBUG=True,
    DATABASES={
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
        }
    },
    ROOT_URLCONF=APP+'.urls',
    INSTALLED_APPS=(
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.admin',
        APP,
    ),
    MIDDLEWARE_CLASSES=(
        'django.middleware.common.CommonMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ),
    TEMPLATES=[
        # Anymail doesn't have any templates, but tests need a TEMPLATES
        # setting to avoid warnings from the Django 1.8+ test client.
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
        },
    ],
)

# Initialize Django app registry
setup()


def runtests(*args):
    test_runner = TestRunner(verbosity=1)
    test_labels = args if len(args) > 0 else ['tests']
    failures = test_runner.run_tests(test_labels)
    sys.exit(failures)

if __name__ == '__main__':
    runtests(*sys.argv[1:])
