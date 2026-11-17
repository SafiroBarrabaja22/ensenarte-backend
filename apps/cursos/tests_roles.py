"""Pruebas de control de acceso por rol en las vistas de cursos y panel."""

import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import URLResolver, get_resolver
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.views import APIView

from apps.usuarios.roles import (
    ROL_ADMINISTRADOR,
    ROL_CREADOR,
    ROL_ESTUDIANTE,
    ROL_INTERPRETE,
    ROL_PROFESOR,
    asignar_rol,
)

from .models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta

MEDIA_TEMPORAL = tempfile.mkdtemp(prefix="ensenarte-pruebas-")


def imagen(nombre="prueba.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buffer, format="PNG")
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type="image/png")


def gif(nombre="sena.gif"):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buffer, format="GIF")
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type="image/gif")


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class RolesTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        self.usuarios = {}
        for nombre, rol in (
            ("estudiante", ROL_ESTUDIANTE),
            ("profesor", ROL_PROFESOR),
            ("profesor2", ROL_PROFESOR),
            ("interprete", ROL_INTERPRETE),
            ("creador", ROL_CREADOR),
            ("admin", ROL_ADMINISTRADOR),
        ):
            usuario = User.objects.create_user(nombre, password="ClaveSegura123")
            asignar_rol(usuario, rol)
            self.usuarios[nombre] = usuario
        self.sin_rol = User.objects.create_user("sinrol", password="ClaveSegura123")

        self.curso_propio = Curso.objects.create(
            nombre="propio", titulo="Propio", portada_curso="",
            creado_por=self.usuarios["profesor"],
        )
        self.curso_ajeno = Curso.objects.create(
            nombre="ajeno", titulo="Ajeno", portada_curso="",
            creado_por=self.usuarios["profesor2"],
        )
        self.pregunta_ajena = Pregunta.objects.create(curso=self.curso_ajeno, texto="P?")
        self.opcion_ajena = OpcionPregunta.objects.create(
            pregunta=self.pregunta_ajena, texto="A", es_correcta=True
        )
        self.pregunta_propia = Pregunta.objects.create(curso=self.curso_propio, texto="Q?")
        self.palabra_ajena = PalabraDiccionario.objects.create(
            curso=self.curso_ajeno, titulo="Hola", imagen_frontal="", video_gif=""
        )

    def como(self, nombre):
        self.client.force_authenticate(self.usuarios[nombre] if nombre else None)

    # --- Publico y aprendizaje -------------------------------------------

    def test_catalogo_es_publico(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/cursos/").status_code, status.HTTP_200_OK)

    def test_cualquier_rol_puede_aprender(self):
        for nombre in self.usuarios:
            self.como(nombre)
            respuesta = self.client.get("/api/progreso/")
            self.assertEqual(respuesta.status_code, status.HTTP_200_OK, nombre)

    def test_usuario_sin_rol_no_puede_aprender(self):
        self.client.force_authenticate(self.sin_rol)
        self.assertEqual(self.client.get("/api/progreso/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.get("/api/cursos/propio/diccionario/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # --- Panel: acceso por rol -------------------------------------------

    def test_estudiante_e_interprete_no_entran_al_panel_de_contenido(self):
        for nombre in ("estudiante", "interprete"):
            self.como(nombre)
            for ruta in ("/api/panel/resumen/", "/api/panel/cursos/", "/api/panel/preguntas/"):
                self.assertEqual(
                    self.client.get(ruta).status_code, status.HTTP_403_FORBIDDEN, (nombre, ruta)
                )
            self.assertEqual(
                self.client.post("/api/panel/cursos/", {}, format="json").status_code,
                status.HTTP_403_FORBIDDEN,
            )

    def test_profesor_crea_curso_y_queda_como_dueno(self):
        self.como("profesor")
        respuesta = self.client.post(
            "/api/panel/cursos/",
            {"nombre": "nuevo", "titulo": "Nuevo", "portada_curso": "x.png"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED, respuesta.data)
        self.assertEqual(
            Curso.objects.get(nombre="nuevo").creado_por, self.usuarios["profesor"]
        )

    # --- Panel: permiso a nivel de objeto --------------------------------

    def test_profesor_solo_lista_sus_cursos(self):
        self.como("profesor")
        nombres = [c["nombre"] for c in self.client.get("/api/panel/cursos/").data["results"]]
        self.assertEqual(nombres, ["propio"])

    def test_profesor_edita_su_curso_pero_no_el_de_otro(self):
        self.como("profesor")
        propio = self.client.patch(
            f"/api/panel/cursos/{self.curso_propio.id}/", {"titulo": "Cambio"}, format="json"
        )
        self.assertEqual(propio.status_code, status.HTTP_200_OK)
        for metodo in ("get", "patch", "delete"):
            respuesta = getattr(self.client, metodo)(
                f"/api/panel/cursos/{self.curso_ajeno.id}/", {"titulo": "X"}, format="json"
            )
            self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN, metodo)
        self.assertTrue(Curso.objects.filter(pk=self.curso_ajeno.pk).exists())

    def test_profesor_no_toca_contenido_de_curso_ajeno(self):
        self.como("profesor")
        casos = [
            ("post", "/api/panel/preguntas/", {"curso": self.curso_ajeno.id, "texto": "Nueva"}),
            ("patch", f"/api/panel/preguntas/{self.pregunta_ajena.id}/", {"texto": "X"}),
            ("patch", f"/api/panel/preguntas/{self.pregunta_propia.id}/", {"curso": self.curso_ajeno.id}),
            ("post", "/api/panel/opciones/", {"pregunta": self.pregunta_ajena.id, "texto": "B"}),
            ("delete", f"/api/panel/opciones/{self.opcion_ajena.id}/", None),
            ("post", "/api/panel/diccionario/", {
                "curso": self.curso_ajeno.id, "titulo": "Adios",
                "imagen_frontal": "a.png", "video_gif": "a.gif",
            }),
            ("delete", f"/api/panel/diccionario/{self.palabra_ajena.id}/", None),
            ("post", "/api/panel/diccionario/reordenar/", {
                "curso": self.curso_ajeno.id, "ids": [self.palabra_ajena.id],
            }),
        ]
        for metodo, ruta, datos in casos:
            respuesta = getattr(self.client, metodo)(ruta, datos, format="json")
            self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN, (metodo, ruta))

    def test_profesor_crea_pregunta_en_su_curso(self):
        self.como("profesor")
        respuesta = self.client.post(
            "/api/panel/preguntas/", {"curso": self.curso_propio.id, "texto": "Nueva"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_creador_y_administrador_editan_cualquier_curso(self):
        for nombre in ("creador", "admin"):
            self.como(nombre)
            respuesta = self.client.patch(
                f"/api/panel/cursos/{self.curso_ajeno.id}/", {"titulo": nombre}, format="json"
            )
            self.assertEqual(respuesta.status_code, status.HTTP_200_OK, nombre)
            listado = self.client.get("/api/panel/cursos/").data["results"]
            self.assertEqual(len(listado), 2, nombre)

    # --- Gifs y biblioteca -----------------------------------------------

    def test_interprete_sube_gif_a_cualquier_curso(self):
        self.como("interprete")
        respuesta = self.client.post(
            f"/api/panel/preguntas/{self.pregunta_ajena.id}/gif/", {"gif": gif()}, format="multipart"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_profesor_no_sube_gif_a_curso_ajeno(self):
        self.como("profesor")
        respuesta = self.client.post(
            f"/api/panel/diccionario/{self.palabra_ajena.id}/gif/", {"gif": gif()}, format="multipart"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_estudiante_no_sube_gifs(self):
        self.como("estudiante")
        respuesta = self.client.post(
            f"/api/panel/preguntas/{self.pregunta_propia.id}/gif/", {"gif": gif()}, format="multipart"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_biblioteca_solo_la_escriben_interprete_y_administrador(self):
        for nombre, esperado in (
            ("interprete", status.HTTP_201_CREATED),
            ("admin", status.HTTP_201_CREATED),
            ("profesor", status.HTTP_403_FORBIDDEN),
            ("creador", status.HTTP_403_FORBIDDEN),
            ("estudiante", status.HTTP_403_FORBIDDEN),
        ):
            self.como(nombre)
            respuesta = self.client.post(
                "/api/panel/recursos/",
                {"nombre": f"r-{nombre}", "archivo": imagen(), "categoria": "insignia"},
                format="multipart",
            )
            self.assertEqual(respuesta.status_code, esperado, (nombre, respuesta.data))

    def test_estudiante_lee_solo_avatares(self):
        self.como("admin")
        self.client.post(
            "/api/panel/recursos/",
            {"nombre": "insignia", "archivo": imagen(), "categoria": "insignia"},
            format="multipart",
        )
        self.client.post(
            "/api/panel/recursos/",
            {"nombre": "avatar", "archivo": imagen(), "categoria": "avatar"},
            format="multipart",
        )
        self.como("estudiante")
        respuesta = self.client.get("/api/panel/recursos/")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual([r["nombre"] for r in respuesta.data], ["avatar"])


class PermisosExplicitosTests(APITestCase):
    """Ninguna vista de la API puede depender del permiso por defecto."""

    def _recorrer(self, patrones, prefijo=""):
        for patron in patrones:
            if isinstance(patron, URLResolver):
                yield from self._recorrer(patron.url_patterns, prefijo + str(patron.pattern))
            else:
                yield prefijo + str(patron.pattern), patron.callback

    def test_todas_las_vistas_declaran_permission_classes(self):
        revisadas = 0
        for ruta, vista in self._recorrer(get_resolver().url_patterns):
            clase = getattr(vista, "cls", None)
            if clase is None or not issubclass(clase, APIView):
                continue
            initkwargs = getattr(vista, "initkwargs", None) or {}
            permisos = initkwargs.get("permission_classes", clase.permission_classes)
            self.assertIsNot(permisos, APIView.permission_classes, f"{ruta} usa el permiso por defecto")
            self.assertTrue(permisos, f"{ruta} tiene permission_classes vacio")
            revisadas += 1
        self.assertGreater(revisadas, 20)
