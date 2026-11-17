"""
Fixtures compartidas por la suite de pytest.

Todo se crea en una base SQLite en memoria (config/settings_pruebas.py): las
pruebas nunca leen la base de desarrollo. Las fixtures `crear_*` son factories:
devuelven una funcion para crear tantos objetos como haga falta.
"""

import io
import itertools

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.cursos.models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta
from apps.usuarios.roles import (
    ROL_ADMINISTRADOR,
    ROL_CREADOR,
    ROL_ESTUDIANTE,
    ROL_INTERPRETE,
    ROL_PROFESOR,
    asignar_rol,
)

CLAVE = "ClaveSegura123!"


@pytest.fixture(autouse=True)
def cache_limpia():
    """Los limites de intentos y bloqueos de login viven en la cache: cada prueba empieza de cero."""
    cache.clear()
    yield
    cache.clear()


# ------------------------------------------------------------------ Clientes


@pytest.fixture
def api():
    """Cliente sin autenticar."""
    return APIClient()


@pytest.fixture
def como():
    """como(usuario) -> cliente autenticado como ese usuario (sin pasar por JWT)."""
    def _como(usuario):
        cliente = APIClient()
        cliente.force_authenticate(usuario)
        return cliente
    return _como


@pytest.fixture
def con_jwt(api):
    """con_jwt(usuario) -> cliente que se autentica de verdad con el login JWT."""
    def _con_jwt(usuario, clave=CLAVE):
        respuesta = api.post(
            "/api/auth/login/", {"username": usuario.username, "password": clave}, format="json"
        )
        assert respuesta.status_code == 200, respuesta.data
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['access']}")
        cliente.tokens = respuesta.data
        return cliente
    return _con_jwt


# ------------------------------------------------------------------ Usuarios


@pytest.fixture
def crear_usuario(db):
    numeros = itertools.count(1)

    def _crear(rol=None, nombre=None, clave=CLAVE, **extra):
        nombre = nombre or f"usuario{next(numeros)}"
        usuario = User.objects.create_user(
            nombre, email=f"{nombre}@correo.com", password=clave, **extra
        )
        if rol:
            asignar_rol(usuario, rol)
        return usuario
    return _crear


@pytest.fixture
def estudiante(crear_usuario):
    return crear_usuario(ROL_ESTUDIANTE, "estudiante")


@pytest.fixture
def profesor(crear_usuario):
    return crear_usuario(ROL_PROFESOR, "profesor")


@pytest.fixture
def profesor2(crear_usuario):
    return crear_usuario(ROL_PROFESOR, "profesor2")


@pytest.fixture
def interprete(crear_usuario):
    return crear_usuario(ROL_INTERPRETE, "interprete")


@pytest.fixture
def creador(crear_usuario):
    return crear_usuario(ROL_CREADOR, "creador")


@pytest.fixture
def administrador(crear_usuario):
    return crear_usuario(ROL_ADMINISTRADOR, "administrador")


@pytest.fixture
def sin_rol(crear_usuario):
    return crear_usuario(None, "sinrol")


# ------------------------------------------------------------------ Contenido


@pytest.fixture
def crear_curso(db):
    """crear_curso(nombre, creado_por, preguntas=3, palabras=2, ...) con 4 opciones por pregunta."""
    def _crear(nombre="abecedario", creado_por=None, preguntas=3, palabras=2, activo=True, **extra):
        curso = Curso.objects.create(
            nombre=nombre, titulo=nombre.title(), portada_curso="portada.png",
            creado_por=creado_por, activo=activo, **extra,
        )
        for i in range(preguntas):
            pregunta = Pregunta.objects.create(curso=curso, texto=f"Pregunta {i + 1}?")
            for j, letra in enumerate("ABCD"):
                OpcionPregunta.objects.create(
                    pregunta=pregunta, texto=f"{letra}{i}", es_correcta=(j == 0)
                )
        for i in range(palabras):
            PalabraDiccionario.objects.create(
                curso=curso, titulo=f"Palabra {i + 1}", imagen_frontal=f"p{i}.png",
                video_gif=f"p{i}.gif", orden=i + 1,
            )
        return curso
    return _crear


@pytest.fixture
def curso(crear_curso, profesor):
    """Curso de `profesor` con 3 preguntas y 2 palabras."""
    return crear_curso("abecedario", creado_por=profesor)


@pytest.fixture
def curso_ajeno(crear_curso, profesor2):
    """Curso de `profesor2`."""
    return crear_curso("saludos", creado_por=profesor2)


def opcion_correcta(pregunta_id):
    return OpcionPregunta.objects.get(pregunta_id=pregunta_id, es_correcta=True)


def opcion_incorrecta(pregunta_id):
    return OpcionPregunta.objects.filter(pregunta_id=pregunta_id, es_correcta=False).first()


# ------------------------------------------------------------------ Archivos


def _archivo(nombre, formato, tipo):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="teal").save(buffer, format=formato)
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type=tipo)


@pytest.fixture
def png():
    return lambda nombre="imagen.png": _archivo(nombre, "PNG", "image/png")


@pytest.fixture
def gif():
    return lambda nombre="sena.gif": _archivo(nombre, "GIF", "image/gif")
