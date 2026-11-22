"""
Configuracion de produccion (docs/DESPLIEGUE.md): /media/ servido por Django
con cabeceras de seguridad, validacion de CSRF_TRUSTED_ORIGINS y WhiteNoise.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from config.media import POLITICA_MEDIA
from config.settings import validar_origenes_cors

# Algunas respuestas pasan por el middleware de sesion y autenticacion.
pytestmark = pytest.mark.django_db


@pytest.fixture
def archivo_media():
    ruta = Path(settings.MEDIA_ROOT) / "biblioteca" / "prueba-despliegue.png"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"\x89PNG\r\n\x1a\nnoimporta")
    yield "/media/biblioteca/prueba-despliegue.png"
    ruta.unlink()


def test_media_se_sirve_con_cabeceras_de_seguridad(client, archivo_media):
    respuesta = client.get(archivo_media)
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "image/png"
    assert respuesta["Content-Security-Policy"] == POLITICA_MEDIA
    assert "sandbox" in respuesta["Content-Security-Policy"]
    assert respuesta["X-Content-Type-Options"] == "nosniff"
    respuesta.close()  # FileResponse deja el archivo abierto hasta cerrarla


def test_media_no_permite_salir_de_la_carpeta(client):
    # Django responde 400 (ruta sospechosa) o 404; nunca el archivo.
    for ruta in ("/media/../config/settings.py", "/media/%2e%2e/config/settings.py",
                 "/media/biblioteca/../../config/settings.py"):
        respuesta = client.get(ruta)
        assert respuesta.status_code in (400, 404), ruta


@override_settings(SERVIR_MEDIA=False)
def test_media_desactivada_responde_404(client, archivo_media):
    assert client.get(archivo_media).status_code == 404


def test_media_inexistente_responde_404(client):
    assert client.get("/media/biblioteca/no-existe.png").status_code == 404


def test_media_lleva_cabeceras_cors_para_el_frontend(client, archivo_media):
    respuesta = client.get(archivo_media, HTTP_ORIGIN="http://localhost:5500")
    assert respuesta["Access-Control-Allow-Origin"] == "http://localhost:5500"
    respuesta.close()


@pytest.mark.parametrize("origen", [
    "https://cachyos-x8664.tailb93c3e.ts.net",
    "https://safirobarrabaja22.github.io",
])
def test_origenes_de_produccion_validos(origen):
    assert validar_origenes_cors([origen]) == [origen]


@pytest.mark.parametrize("origen", [
    "*", "https://*.ts.net", "https://safirobarrabaja22.github.io/ensenarte-frontend",
    "https://safirobarrabaja22.github.io/", "cachyos-x8664.tailb93c3e.ts.net",
])
def test_origenes_mal_escritos_detienen_el_arranque(origen):
    with pytest.raises(ImproperlyConfigured):
        validar_origenes_cors([origen])


def test_whitenoise_va_despues_de_security_middleware():
    middleware = settings.MIDDLEWARE
    assert middleware.index("whitenoise.middleware.WhiteNoiseMiddleware") == (
        middleware.index("django.middleware.security.SecurityMiddleware") + 1
    )


# ------------------------------------------------------------------ Base de datos por variables (Docker)


def _bases_con(entorno):
    """DATABASES de config.settings cargado en un proceso aparte con ese entorno."""
    import json
    import os
    import subprocess
    import sys

    variables = {k: v for k, v in os.environ.items() if not k.startswith(("DB_", "DATABASE_URL"))}
    variables.update({"SECRET_KEY": "x", "DEBUG": "True", **entorno})
    codigo = (
        "import json, django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings';"
        "from django.conf import settings; d = settings.DATABASES['default'];"
        "print(json.dumps({k: str(d.get(k)) for k in ('ENGINE','NAME','USER','HOST','PORT')}))"
    )
    salida = subprocess.run([sys.executable, "-c", codigo], env=variables, capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parent.parent, check=True)
    return json.loads(salida.stdout.strip().splitlines()[-1])


def test_db_name_arma_la_conexion_mysql_por_variables():
    bd = _bases_con({"DB_NAME": "ensenarte", "DB_USER": "app", "DB_PASSWORD": "x",
                     "DB_HOST": "host.docker.internal", "DB_PORT": "3307", "DATABASE_URL": "sqlite:///otra.sqlite3"})
    assert bd == {"ENGINE": "django.db.backends.mysql", "NAME": "ensenarte", "USER": "app",
                  "HOST": "host.docker.internal", "PORT": "3307"}


def test_sin_db_name_sigue_usando_database_url():
    bd = _bases_con({"DB_NAME": "", "DATABASE_URL": "mysql://dev:x@127.0.0.1:3306/proyecto_local"})
    assert bd["ENGINE"] == "django.db.backends.mysql" and bd["NAME"] == "proyecto_local"


def test_las_pruebas_ignoran_db_name_del_entorno():
    """settings_pruebas.py vacia DB_NAME: las pruebas nunca van a la base del .env."""
    assert settings.DATABASES["default"]["ENGINE"] != "django.db.backends.mysql" or \
        settings.DATABASES["default"]["NAME"] not in {"proyecto_v2"}
    import os
    assert os.environ.get("DB_NAME") == ""
