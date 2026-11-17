"""Pruebas de la configuracion de JWT y CORS."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from config.settings import validar_origenes_cors

from .roles import ROL_ESTUDIANTE, asignar_rol

# Clave al azar en cada ejecucion: ninguna contrasena queda escrita en el codigo.
CLAVE = secrets.token_urlsafe(12) + "Aa1!"


ORIGEN_LOCAL = "http://localhost:5500"
ORIGEN_PRODUCCION = "https://safirobarrabaja22.github.io"


class JWTTests(APITestCase):
    def setUp(self):
        usuario = User.objects.create_user("ana", password=CLAVE)
        asignar_rol(usuario, ROL_ESTUDIANTE)

    def login(self):
        respuesta = self.client.post(
            reverse("login"), {"username": "ana", "password": CLAVE}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        return respuesta.data["access"], respuesta.data["refresh"]

    def refrescar(self, refresh):
        return self.client.post(reverse("token_refresh"), {"refresh": refresh}, format="json")

    def test_tiempos_de_expiracion(self):
        jwt = settings.SIMPLE_JWT
        self.assertLessEqual(jwt["ACCESS_TOKEN_LIFETIME"], timedelta(minutes=30))
        self.assertLessEqual(jwt["REFRESH_TOKEN_LIFETIME"], timedelta(days=14))
        self.assertTrue(jwt["ROTATE_REFRESH_TOKENS"])
        self.assertTrue(jwt["BLACKLIST_AFTER_ROTATION"])

    def test_refresh_entrega_tokens_nuevos_y_el_viejo_deja_de_servir(self):
        _, refresh = self.login()
        primera = self.refrescar(refresh)
        self.assertEqual(primera.status_code, status.HTTP_200_OK)
        self.assertIn("access", primera.data)
        self.assertNotEqual(primera.data["refresh"], refresh)

        reutilizado = self.refrescar(refresh)
        self.assertEqual(reutilizado.status_code, status.HTTP_401_UNAUTHORIZED)

        self.assertEqual(self.refrescar(primera.data["refresh"]).status_code, status.HTTP_200_OK)

    def test_logout_invalida_el_refresh_en_el_servidor(self):
        _, refresh = self.login()
        salida = self.client.post(reverse("logout"), {"refresh": refresh}, format="json")
        self.assertEqual(salida.status_code, status.HTTP_200_OK)
        self.assertEqual(self.refrescar(refresh).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_funciona_sin_access_valido(self):
        _, refresh = self.login()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer vencido")
        salida = self.client.post(reverse("logout"), {"refresh": refresh}, format="json")
        self.assertEqual(salida.status_code, status.HTTP_200_OK)

    def test_access_invalido_responde_401_para_que_el_frontend_refresque(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer token-vencido")
        self.assertEqual(self.client.get("/api/progreso/").status_code, status.HTTP_401_UNAUTHORIZED)


class CORSTests(APITestCase):
    def test_configuracion_sin_comodines(self):
        self.assertFalse(settings.CORS_ALLOW_ALL_ORIGINS)
        self.assertEqual(settings.CORS_ALLOWED_ORIGIN_REGEXES, [])
        self.assertFalse(settings.CORS_ALLOW_CREDENTIALS)
        self.assertTrue(settings.CORS_ALLOWED_ORIGINS)
        for origen in settings.CORS_ALLOWED_ORIGINS:
            self.assertNotIn("*", origen)

    def test_validacion_rechaza_origenes_peligrosos_o_mal_escritos(self):
        for lista in (
            ["*"],
            ["https://*.github.io"],
            ["null"],
            [],
            ["safirobarrabaja22.github.io"],
            ["https://safirobarrabaja22.github.io/"],
            ["https://safirobarrabaja22.github.io/ensenarte-frontend"],
        ):
            with self.assertRaises(ImproperlyConfigured, msg=lista):
                validar_origenes_cors(lista)
        self.assertEqual(
            validar_origenes_cors([ORIGEN_LOCAL, ORIGEN_PRODUCCION]),
            [ORIGEN_LOCAL, ORIGEN_PRODUCCION],
        )

    @override_settings(CORS_ALLOWED_ORIGINS=[ORIGEN_LOCAL, ORIGEN_PRODUCCION])
    def test_origen_permitido_recibe_cabecera(self):
        for origen in (ORIGEN_LOCAL, ORIGEN_PRODUCCION):
            respuesta = self.client.get("/api/cursos/", HTTP_ORIGIN=origen)
            self.assertEqual(respuesta.headers.get("Access-Control-Allow-Origin"), origen)

    @override_settings(CORS_ALLOWED_ORIGINS=[ORIGEN_LOCAL, ORIGEN_PRODUCCION])
    def test_origen_no_permitido_no_recibe_cabecera(self):
        for origen in ("https://sitio-malicioso.example", "https://otro.github.io", "null"):
            respuesta = self.client.get("/api/cursos/", HTTP_ORIGIN=origen)
            self.assertNotIn("Access-Control-Allow-Origin", respuesta.headers, origen)

    @override_settings(CORS_ALLOWED_ORIGINS=[ORIGEN_PRODUCCION])
    def test_preflight_de_origen_permitido(self):
        respuesta = self.client.options(
            "/api/auth/login/",
            HTTP_ORIGIN=ORIGEN_PRODUCCION,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
        )
        self.assertEqual(respuesta.headers.get("Access-Control-Allow-Origin"), ORIGEN_PRODUCCION)
        self.assertIn("authorization", respuesta.headers.get("Access-Control-Allow-Headers", ""))
