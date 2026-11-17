"""Pruebas de la documentacion OpenAPI (drf-spectacular)."""

from io import StringIO

from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APITestCase

from config.etiquetas_api import DESCRIPCION_ETIQUETAS

ETIQUETAS = {etiqueta["name"] for etiqueta in DESCRIPCION_ETIQUETAS}
# Endpoints que se usan sin token (los demas deben pedir el JWT en Swagger UI).
PUBLICOS = {
    "/api/auth/login/", "/api/auth/refresh/", "/api/auth/verify/", "/api/auth/logout/",
    "/api/auth/registro/", "/api/auth/recuperar/solicitar/", "/api/auth/recuperar/confirmar/",
    "/api/cursos/", "/api/cursos/{slug}/",
}


class DocumentacionTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.esquema = SchemaGenerator().get_schema(request=None, public=True)

    def test_rutas_de_documentacion_responden_sin_token(self):
        esquema = self.client.get("/api/schema/")
        self.assertEqual(esquema.status_code, 200)
        self.assertIn(b"openapi", esquema.content)
        for ruta in ("/api/docs/", "/api/redoc/"):
            self.assertEqual(self.client.get(ruta).status_code, 200, ruta)

    def test_swagger_ui_conserva_el_token_jwt(self):
        html = self.client.get("/api/docs/").content.decode()
        self.assertIn("persistAuthorization", html)
        self.assertNotIn("@latest", html)

    def test_informacion_del_proyecto(self):
        info = self.esquema["info"]
        self.assertEqual(info["title"], "API de enSEÑArte")
        self.assertTrue(info["version"])
        self.assertIn("Authorize", info["description"])

    def test_esquema_jwt_bearer(self):
        seguridad = self.esquema["components"]["securitySchemes"]["jwtAuth"]
        self.assertEqual((seguridad["type"], seguridad["scheme"]), ("http", "bearer"))

    def test_cada_operacion_esta_documentada_y_etiquetada(self):
        for ruta, operaciones in self.esquema["paths"].items():
            for metodo, operacion in operaciones.items():
                nombre = f"{metodo.upper()} {ruta}"
                self.assertTrue(operacion.get("summary"), f"{nombre} sin resumen")
                self.assertTrue(operacion.get("description"), f"{nombre} sin descripcion")
                self.assertEqual(len(operacion.get("tags", [])), 1, nombre)
                self.assertIn(operacion["tags"][0], ETIQUETAS, nombre)
                exito = [c for c in operacion["responses"] if c.startswith("2")]
                self.assertTrue(exito, f"{nombre} sin respuesta exitosa")

    def test_endpoints_protegidos_piden_jwt_y_documentan_401(self):
        for ruta, operaciones in self.esquema["paths"].items():
            if ruta in PUBLICOS:
                continue
            for metodo, operacion in operaciones.items():
                nombre = f"{metodo.upper()} {ruta}"
                self.assertIn({"jwtAuth": []}, operacion.get("security", []), nombre)
                self.assertNotIn({}, operacion.get("security", []), f"{nombre} figura como publico")
                self.assertIn("401", operacion["responses"], nombre)

    def test_endpoints_publicos_no_muestran_candado(self):
        for ruta in PUBLICOS:
            for metodo, operacion in self.esquema["paths"][ruta].items():
                seguridad = operacion.get("security")
                self.assertIn(seguridad, (None, [], [{}]), f"{metodo.upper()} {ruta}: {seguridad}")

    def test_generacion_sin_avisos(self):
        salida, errores = StringIO(), StringIO()
        call_command("spectacular", "--validate", "--fail-on-warn", stdout=salida, stderr=errores)
