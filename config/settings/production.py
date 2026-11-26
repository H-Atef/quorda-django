
from .base import *  # noqa: F401,F403
from .base import DEBUG, env_bool

if DEBUG:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('DEBUG must be False when using config.settings.production.')

SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', default=True)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
