"""
Configuracion para la suite de pruebas (pytest y `manage.py test`).

Nunca usa la base de datos de desarrollo: el .env local apunta a un MySQL
compartido. En local y en la CI (.github/workflows/ci.yml) usa SQLite en
memoria. Las variables se fijan ANTES de importar settings.py, y
django-environ no sobrescribe variables ya definidas.
"""

import os
import tempfile

# Sin PRUEBAS_DATABASE_URL (lo normal, tambien en la CI) se usa SQLite en memoria.
# Se define a mano solo para correr las pruebas de triggers y procedimientos
# contra MySQL (proyecto_pruebas; ver README). Es otra variable a proposito: un
# DATABASE_URL de desarrollo nunca debe terminar en las pruebas.
os.environ["DATABASE_URL"] = os.environ.get("PRUEBAS_DATABASE_URL", "sqlite://:memory:")

# Bases compartidas a las que las pruebas NUNCA deben conectarse (Django crearia
# test_<nombre> en ese servidor). Se puede ampliar con BASES_PROTEGIDAS=a,b.
from urllib.parse import urlsplit  # noqa: E402

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

BASES_PROTEGIDAS = {"proyecto_v2", *filter(None, os.environ.get("BASES_PROTEGIDAS", "").split(","))}
_base_pruebas = urlsplit(os.environ["DATABASE_URL"]).path.lstrip("/")
if _base_pruebas in BASES_PROTEGIDAS:
    raise ImproperlyConfigured(
        f"Las pruebas no pueden apuntar a '{_base_pruebas}' (base compartida). "
        "Usa PRUEBAS_DATABASE_URL con proyecto_pruebas."
    )
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-no-usar-en-produccion")
# Con DEBUG=False settings.py activa SECURE_SSL_REDIRECT y el cliente de pruebas
# (http) recibiria 301. Django vuelve a poner DEBUG=False al correr las pruebas.
os.environ["DEBUG"] = "True"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:5500,http://127.0.0.1:5500"

from config.settings import *  # noqa: E402,F401,F403

# Hasher rapido: PBKDF2 hace que cada usuario creado tarde ~0,3 s.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Las subidas (gifs, imagenes) van a una carpeta temporal, no a media/.
MEDIA_ROOT = tempfile.mkdtemp(prefix="ensenarte-pruebas-media-")

# El almacenamiento de produccion (WhiteNoise con manifiesto) exige correr
# collectstatic antes; en las pruebas basta el almacenamiento normal.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# WhiteNoise avisa si STATIC_ROOT no existe (en local nadie corre collectstatic).
STATIC_ROOT = tempfile.mkdtemp(prefix="ensenarte-pruebas-static-")

# Cache en memoria (la de base de datos necesita su tabla). conftest.py la
# limpia antes de cada prueba para que los limites de intentos no se mezclen.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# Los correos de recuperacion se envian en el mismo hilo para poder revisarlos.
CORREOS_EN_SEGUNDO_PLANO = False

# El limite general (anon/user) no debe interferir con las pruebas que hacen
# muchas peticiones seguidas; tests/test_seguridad_acceso.py lo prueba aparte.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],  # noqa: F405
        "anon": "100000/min",
        "user": "100000/min",
    },
}
