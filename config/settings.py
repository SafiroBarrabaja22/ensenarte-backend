"""
Configuracion de Django para el backend de enSEÑArte.

Toda la configuracion sensible se lee de variables de entorno (archivo .env).
Ver .env.example para la lista completa.
"""

from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5500", "http://127.0.0.1:5500"]),
)
environ.Env.read_env(BASE_DIR / ".env")

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
    # Lista negra de refresh tokens: permite invalidarlos al cerrar sesion y
    # al rotarlos. Sus tablas vienen en las migraciones del propio paquete.
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # Documentacion OpenAPI: /api/schema/, /api/docs/ (Swagger UI), /api/redoc/
    "drf_spectacular",
    # Propias
    "apps.usuarios",
    "apps.cursos",
    "apps.evaluacion_camara",
    "apps.correos",
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
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}


# ==========================================================
# DOCUMENTACION OPENAPI (drf-spectacular)
# ==========================================================

from config.etiquetas_api import DESCRIPCION_ETIQUETAS  # noqa: E402

SPECTACULAR_SETTINGS = {
    "TITLE": "API de enSEÑArte",
    "DESCRIPTION": (
        "API REST de enSEÑArte, aplicativo para aprender Lengua de Señas "
        "Colombiana (LSC): catálogo de cursos, diccionario visual, evaluaciones "
        "por preguntas y con cámara, y panel administrativo por roles.\n\n"
        "**Cómo probar los endpoints protegidos desde esta página**\n\n"
        "1. Abre `POST /api/auth/login/`, pulsa *Try it out* y envía tu usuario y "
        "contraseña (cuentas de demostración en el README del backend).\n"
        "2. Copia el valor de `access` de la respuesta.\n"
        "3. Pulsa el botón **Authorize** (arriba a la derecha), pega el token "
        "**sin** escribir `Bearer` y confirma.\n"
        "4. Desde ahí, cada *Try it out* envía `Authorization: Bearer <token>`. "
        "El token dura 15 minutos; si responde 401, repite el login o usa "
        "`POST /api/auth/refresh/`.\n\n"
        "**Roles:** Estudiante, Profesor, Interprete, CreadorDeCursos y "
        "Administrador. Cada endpoint indica qué roles lo pueden usar; con otro "
        "rol responde 403."
    ),
    "VERSION": "1.0.0",
    "TAGS": DESCRIPCION_ETIQUETAS,
    # El esquema no se lista a si mismo en la documentacion.
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/",
    # Separa esquemas de entrada y salida: los campos de archivo (gif, imagen)
    # se muestran como carga de archivo en Swagger UI.
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,  # el token sobrevive a recargar la pagina
        "tryItOutEnabled": True,
        "filter": True,
        "docExpansion": "list",
    },
    # Versiones fijas de los recursos de Swagger UI y ReDoc (no "@latest").
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14",
    "SWAGGER_UI_FAVICON_HREF": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/favicon-32x32.png",
    "REDOC_DIST": "https://cdn.jsdelivr.net/npm/redoc@2.1.5",
}

# - access: corto (15 min). Viaja en cada peticion; si alguien lo roba, sirve poco
#   tiempo. El frontend lo renueva solo, sin que el usuario lo note.
# - refresh: 7 dias. Con ROTATE cada renovacion entrega un refresh nuevo y el
#   anterior queda en la lista negra: un refresh robado deja de servir en cuanto
#   el usuario legitimo renueva, y la sesion solo vence tras 7 dias SIN uso.
# - Al cerrar sesion el frontend llama a /api/auth/logout/ y el refresh se
#   invalida en el servidor (no basta con borrarlo del navegador).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESO_MINUTOS", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESCO_DIAS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# ==========================================================
# CORS (el frontend vive en otro dominio/puerto)
# ==========================================================

# Explicacion en lenguaje llano: docs/SEGURIDAD.md.
# La lista se lee SIEMPRE de la variable de entorno CORS_ALLOWED_ORIGINS
# (separada por comas). El valor por defecto solo cubre desarrollo local; en
# produccion debe incluir https://safirobarrabaja22.github.io (GitHub Pages).


def validar_origenes_cors(origenes):
    """
    Detiene el arranque si la lista de origenes es peligrosa o esta mal escrita.

    Un origen es esquema + dominio (+ puerto), sin ruta ni barra final:
    "https://safirobarrabaja22.github.io", no ".../ensenarte-frontend/".
    """
    if not origenes:
        raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS esta vacia.")
    for origen in origenes:
        if "*" in origen or origen.lower() == "null":
            raise ImproperlyConfigured(
                f"CORS_ALLOWED_ORIGINS no admite comodines ni 'null': {origen!r}"
            )
        partes = urlsplit(origen)
        if partes.scheme not in ("http", "https") or not partes.netloc:
            raise ImproperlyConfigured(f"Origen CORS invalido: {origen!r}")
        if partes.path or partes.query or partes.fragment:
            raise ImproperlyConfigured(
                f"Origen CORS con ruta o barra final: {origen!r}. "
                "Usa solo esquema y dominio, p. ej. https://safirobarrabaja22.github.io"
            )
    return origenes


CORS_ALLOWED_ORIGINS = validar_origenes_cors(env("CORS_ALLOWED_ORIGINS"))
# Nunca abrir a todos los origenes ni usar expresiones regulares.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGIN_REGEXES = []
# La API usa JWT en la cabecera Authorization, no cookies: no hace falta que
# el navegador envie credenciales entre origenes.
CORS_ALLOW_CREDENTIALS = False


# ==========================================================
# CORREO (apps/correos)
# ==========================================================
# Con DEBUG=True los correos se imprimen en la consola del servidor y no se
# envia nada real. Con DEBUG=False se usa SMTP con los datos del entorno.
# EMAIL_BACKEND permite forzar otro backend (p. ej. probar SMTP en local).

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.smtp.EmailBackend"
    ),
)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
# Segundos maximos esperando al servidor SMTP: un SMTP caido no debe colgar
# el registro de un usuario.
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="enSEÑArte <no-responder@ensenarte.local>")

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured("EMAIL_USE_TLS y EMAIL_USE_SSL no pueden estar activos a la vez.")

# URL publica del frontend, para los enlaces de los correos.
URL_FRONTEND = env("URL_FRONTEND", default="http://127.0.0.1:5500")


# ==========================================================
# INTERNACIONALIZACION
# ==========================================================

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True


# ==========================================================
# ARCHIVOS ESTATICOS Y MEDIA
# ==========================================================
# Las imagenes y gifs del curso NO viven aqui: son assets de presentacion
# y estan en el repositorio del frontend. Aqui solo se sirven los archivos
# que sube el usuario (fotos de perfil) y los estaticos del admin de Django.

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

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
