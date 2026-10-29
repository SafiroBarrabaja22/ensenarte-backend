"""
Configuracion de Django para el backend de enSEÑArte.

Toda la configuracion sensible se lee de variables de entorno (archivo .env).
Ver .env.example para la lista completa.
"""

from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5500", "http://127.0.0.1:5500"]),
)
environ.Env.read_env(BASE_DIR / ".env")

CLOUDINARY_CREDENTIALS = {
    "CLOUD_NAME": env("CLOUDINARY_CLOUD_NAME", default=""),
    "API_KEY": env("CLOUDINARY_API_KEY", default=""),
    "API_SECRET": env("CLOUDINARY_API_SECRET", default=""),
}
CLOUDINARY_CONFIGURED = all(CLOUDINARY_CREDENTIALS.values())
if not CLOUDINARY_CONFIGURED:
    raise ImproperlyConfigured(
        "Configura CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY y "
        "CLOUDINARY_API_SECRET para almacenar archivos."
    )
CLOUDINARY_STORAGE = {**CLOUDINARY_CREDENTIALS, "SECURE": True}

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Evaluacion con camara: una sesion cubre el abecedario completo y requiere
# al menos 70 % para aprobar. Se pueden ajustar desde el archivo .env.
EVALUACION_CAMARA_MAX_INTENTOS = env.int("EVALUACION_CAMARA_MAX_INTENTOS", default=50)
EVALUACION_CAMARA_UMBRAL_APROBACION = env.int(
    "EVALUACION_CAMARA_UMBRAL_APROBACION", default=70
)


# ==========================================================
# APLICACIONES
# ==========================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "corsheaders",
    "cloudinary_storage",
    # Propias
    "apps.usuarios",
    "apps.cursos",
    "apps.evaluacion_camara",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ==========================================================
# BASE DE DATOS
# ==========================================================

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}


# ==========================================================
# AUTENTICACION
# ==========================================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ==========================================================
# DJANGO REST FRAMEWORK
# ==========================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# ==========================================================
# EVALUACION CON CAMARA
# ==========================================================
# Aprobado si correctas * 100 >= UMBRAL * total (comparacion en enteros).

EVALUACION_CAMARA_UMBRAL_APROBACION = env.int(
    "EVALUACION_CAMARA_UMBRAL_APROBACION", default=70
)
EVALUACION_CAMARA_MAX_INTENTOS = 50


# ==========================================================
# CORS (el frontend vive en otro dominio/puerto)
# ==========================================================

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = False


# ==========================================================
# INTERNACIONALIZACION
# ==========================================================

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True


# ==========================================================
# ARCHIVOS ESTATICOS Y ALMACENAMIENTO EN LA NUBE
# ==========================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Cloudinary usa MEDIA_URL como prefijo/carpeta para las subidas.
MEDIA_URL = "media/"

STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==========================================================
# SEGURIDAD EN PRODUCCION
# ==========================================================

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
