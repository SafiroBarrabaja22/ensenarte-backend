"""
Validacion de entradas e inyeccion SQL (docs/SEGURIDAD.md, "Inyeccion SQL").

1. Textos con inyeccion SQL se guardan y se buscan como texto literal: no
   alteran la consulta, no dan acceso y no borran nada.
2. Los textos que pasan del limite (config/limites.py y max_length de los
   modelos) responden 400 con el campo que fallo, nunca 500.
"""

import pytest
from django.contrib.auth.models import User
from django.db import connection

from apps.cursos.models import Curso, OpcionPregunta, Pregunta, RecursoVisual
from config.limites import (
    MAX_CORREO,
    MAX_DESCRIPCION_CURSO,
    MAX_NOMBRE_USUARIO,
    MAX_PASSWORD,
    MAX_TOKEN_RECUPERACION,
)

from .conftest import CLAVE

pytestmark = pytest.mark.django_db

# Ataques clasicos: saltarse el WHERE, cerrar la consulta y encadenar otra,
# UNION para leer otras tablas, comentarios para cortar el resto.
INYECCIONES = [
    "' OR '1'='1",
    "' OR 1=1 --",
    "admin'--",
    "'; DROP TABLE cursos_curso; --",
    "\" OR \"\"=\"",
    "1; DELETE FROM auth_user",
    "' UNION SELECT username, password FROM auth_user --",
    "%' OR '%'='",
]


def tabla_existe(nombre):
    return nombre in connection.introspection.table_names()


# ------------------------------------------------------------------ Inyeccion SQL


@pytest.mark.parametrize("ataque", INYECCIONES)
def test_login_con_inyeccion_no_da_acceso(api, estudiante, ataque):
    for datos in ({"username": ataque, "password": ataque},
                  {"username": "estudiante", "password": ataque},
                  {"username": ataque, "password": CLAVE}):
        respuesta = api.post("/api/auth/login/", datos, format="json")
        assert respuesta.status_code == 401, datos
        assert "access" not in respuesta.data


@pytest.mark.parametrize("ataque", INYECCIONES)
def test_registro_guarda_la_inyeccion_como_texto(api, ataque):
    usuarios_antes = User.objects.count()
    respuesta = api.post(
        "/api/auth/registro/",
        {"nombre": ataque, "correo": "nuevo@correo.com", "password": "OtraClave2026!"},
        format="json",
    )
    assert respuesta.status_code == 201
    assert User.objects.count() == usuarios_antes + 1        # ni borro ni creo de mas
    assert User.objects.filter(username=ataque).exists()      # guardado literal
    assert tabla_existe("auth_user")


def test_drop_table_en_un_curso_se_guarda_como_titulo(como, creador, curso):
    ataque = "'; DROP TABLE cursos_curso; --"
    respuesta = como(creador).post(
        "/api/panel/cursos/",
        {"nombre": "ataque", "titulo": ataque, "descripcion": ataque, "portada_curso": "x.png"},
        format="json",
    )
    assert respuesta.status_code == 201
    assert tabla_existe("cursos_curso")
    assert Curso.objects.count() == 2                          # el existente sigue ahi
    assert Curso.objects.get(nombre="ataque").titulo == ataque


def test_inyeccion_en_preguntas_y_opciones_se_guarda_literal(como, creador, curso):
    ataque = "' OR 1=1; DELETE FROM cursos_opcionpregunta; --"
    cliente = como(creador)
    pregunta = cliente.post("/api/panel/preguntas/", {"curso": curso.id, "texto": ataque}, format="json")
    assert pregunta.status_code == 201
    opciones_antes = OpcionPregunta.objects.count()
    opcion = cliente.post(
        "/api/panel/opciones/",
        {"pregunta": pregunta.data["id"], "texto": ataque, "es_correcta": False},
        format="json",
    )
    assert opcion.status_code == 201
    assert OpcionPregunta.objects.count() == opciones_antes + 1
    assert Pregunta.objects.get(pk=pregunta.data["id"]).texto == ataque


@pytest.mark.parametrize("ataque", INYECCIONES)
def test_busqueda_con_inyeccion_no_devuelve_todo(como, interprete, ataque):
    RecursoVisual.objects.create(nombre="logo", archivo="biblioteca/logo.png")
    RecursoVisual.objects.create(nombre="fondo", archivo="biblioteca/fondo.png")
    respuesta = como(interprete).get("/api/panel/recursos/", {"q": ataque})
    assert respuesta.status_code == 200
    assert respuesta.data == []                                # "OR 1=1" no trae los 2


def test_slug_con_inyeccion_en_la_url_responde_404(api):
    assert api.get("/api/cursos/' OR '1'='1/").status_code == 404


# ------------------------------------------------------------------ Longitudes


def largo(n):
    return "a" * n


def correo_de(n):
    return largo(n - len("@correo.com")) + "@correo.com"


@pytest.mark.parametrize("campo, valor", [
    ("nombre", largo(MAX_NOMBRE_USUARIO + 1)),
    ("correo", correo_de(MAX_CORREO + 1)),
    ("password", largo(MAX_PASSWORD + 1)),
])
def test_registro_rechaza_textos_demasiado_largos(api, campo, valor):
    datos = {"nombre": "nuevo", "correo": "nuevo@correo.com", "password": "OtraClave2026!", campo: valor}
    respuesta = api.post("/api/auth/registro/", datos, format="json")
    assert respuesta.status_code == 400
    assert campo in respuesta.data


@pytest.mark.parametrize("campo", ["username", "password"])
def test_login_rechaza_textos_demasiado_largos(api, estudiante, campo):
    datos = {"username": "estudiante", "password": CLAVE, campo: largo(MAX_PASSWORD + MAX_NOMBRE_USUARIO)}
    respuesta = api.post("/api/auth/login/", datos, format="json")
    assert respuesta.status_code == 400
    assert campo in respuesta.data


def test_cambiar_password_rechaza_una_demasiado_larga(como, estudiante):
    respuesta = como(estudiante).post(
        "/api/auth/cambiar-password/",
        {"password_actual": CLAVE, "password_nueva": largo(MAX_PASSWORD + 1)},
        format="json",
    )
    assert respuesta.status_code == 400
    assert "password_nueva" in respuesta.data


def test_recuperacion_rechaza_token_demasiado_largo(api):
    respuesta = api.post(
        "/api/auth/recuperar/confirmar/",
        {"uid": "MQ", "token": largo(MAX_TOKEN_RECUPERACION + 1), "password_nueva": "OtraClave2026!"},
        format="json",
    )
    assert respuesta.status_code == 400
    assert "token" in respuesta.data


def test_descripcion_del_curso_en_el_limite_se_acepta(como, creador):
    respuesta = como(creador).post(
        "/api/panel/cursos/",
        {"nombre": "limite", "titulo": "Limite", "portada_curso": "x.png",
         "descripcion": largo(MAX_DESCRIPCION_CURSO)},
        format="json",
    )
    assert respuesta.status_code == 201


@pytest.mark.parametrize("ruta, datos, campo", [
    ("/api/panel/cursos/", {"nombre": "largo", "titulo": largo(101), "portada_curso": "x.png"}, "titulo"),
    ("/api/panel/cursos/", {"nombre": "largo", "titulo": "T", "portada_curso": "x.png",
                            "descripcion": largo(MAX_DESCRIPCION_CURSO + 1)}, "descripcion"),
    ("/api/panel/cursos/", {"nombre": largo(51), "titulo": "T", "portada_curso": "x.png"}, "nombre"),
    ("/api/panel/preguntas/", {"curso": None, "texto": largo(201)}, "texto"),
    ("/api/panel/diccionario/", {"curso": None, "titulo": largo(101), "imagen_frontal": "a.png",
                                 "video_gif": "a.gif"}, "titulo"),
])
def test_panel_rechaza_textos_demasiado_largos(como, creador, curso, ruta, datos, campo):
    datos = {clave: (curso.id if valor is None else valor) for clave, valor in datos.items()}
    respuesta = como(creador).post(ruta, datos, format="json")
    assert respuesta.status_code == 400
    assert campo in respuesta.data


def test_opcion_demasiado_larga_responde_400(como, creador, curso):
    pregunta = Pregunta.objects.create(curso=curso, texto="Nueva?")
    respuesta = como(creador).post(
        "/api/panel/opciones/", {"pregunta": pregunta.id, "texto": largo(101), "es_correcta": False},
        format="json",
    )
    assert respuesta.status_code == 400
    assert "texto" in respuesta.data
