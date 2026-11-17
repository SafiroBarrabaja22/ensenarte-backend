"""
Configuracion para la suite de pruebas (pytest y `manage.py test`).

Nunca usa la base de datos de desarrollo: el .env local apunta a un MySQL
compartido. Las variables se fijan ANTES de importar settings.py, y
django-environ no sobrescribe variables ya definidas.
"""

import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite://:memory:"

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
