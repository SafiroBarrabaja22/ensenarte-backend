"""Registro, login, JWT, perfil y recuperacion de contrasena."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework_simplejwt.tokens import AccessToken

from apps.cursos.models import RecursoVisual
from apps.usuarios.roles import ROL_ESTUDIANTE

from .conftest import CLAVE

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ Registro


def test_registro_exitoso_crea_estudiante(api):
    respuesta = api.post(
        "/api/auth/registro/",
        {"nombre": "nueva", "correo": "nueva@correo.com", "password": CLAVE},
        format="json",
    )
    assert respuesta.status_code == 201
    assert respuesta.data["usuario"]["roles"] == [ROL_ESTUDIANTE]
    assert User.objects.get(username="nueva").perfil.estrellas == 0


@pytest.mark.parametrize("datos, campo", [
    ({"nombre": "estudiante", "correo": "otro@correo.com", "password": CLAVE}, "nombre"),
    ({"nombre": "otro", "correo": "estudiante@correo.com", "password": CLAVE}, "correo"),
    ({"nombre": "otro", "correo": "otro@correo.com", "password": "12345678"}, "password"),
    ({"nombre": "otro", "correo": "no-es-correo", "password": CLAVE}, "correo"),
    ({"correo": "otro@correo.com", "password": CLAVE}, "nombre"),
])
def test_registro_con_datos_invalidos_responde_400(api, estudiante, datos, campo):
    respuesta = api.post("/api/auth/registro/", datos, format="json")
    assert respuesta.status_code == 400
    assert campo in respuesta.data


# ------------------------------------------------------------------ Login y JWT


def test_login_exitoso_devuelve_tokens_y_roles(api, estudiante):
    respuesta = api.post("/api/auth/login/", {"username": "estudiante", "password": CLAVE}, format="json")
    assert respuesta.status_code == 200
    assert {"access", "refresh", "usuario"} <= set(respuesta.data)
    assert respuesta.data["usuario"]["roles"] == [ROL_ESTUDIANTE]


@pytest.mark.parametrize("usuario, clave", [("estudiante", "ClaveIncorrecta1"), ("no-existe", CLAVE)])
def test_login_con_credenciales_malas_responde_401(api, estudiante, usuario, clave):
    respuesta = api.post("/api/auth/login/", {"username": usuario, "password": clave}, format="json")
    assert respuesta.status_code == 401


def test_login_sin_datos_responde_400(api):
    assert api.post("/api/auth/login/", {}, format="json").status_code == 400


def test_endpoint_protegido_sin_token_responde_401(api):
    assert api.get("/api/auth/perfil/").status_code == 401
    assert api.get("/api/progreso/").status_code == 401


def test_token_expirado_responde_401(api, estudiante):
    token = AccessToken.for_user(estudiante)
    token.set_exp(lifetime=timedelta(seconds=-1))
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    respuesta = api.get("/api/auth/perfil/")
    assert respuesta.status_code == 401
    assert respuesta.data["code"] == "token_not_valid"


def test_token_mal_formado_responde_401(api):
    api.credentials(HTTP_AUTHORIZATION="Bearer esto-no-es-un-jwt")
    assert api.get("/api/auth/perfil/").status_code == 401


def test_flujo_jwt_completo_login_refresh_logout(api, con_jwt, estudiante):
    cliente = con_jwt(estudiante)
    assert cliente.get("/api/auth/perfil/").status_code == 200

    refresh = cliente.tokens["refresh"]
    renovado = api.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    assert renovado.status_code == 200
    assert api.post("/api/auth/verify/", {"token": renovado.data["access"]}, format="json").status_code == 200

    assert api.post("/api/auth/logout/", {"refresh": renovado.data["refresh"]}, format="json").status_code == 200
    assert api.post("/api/auth/refresh/", {"refresh": renovado.data["refresh"]}, format="json").status_code == 401


# ------------------------------------------------------------------ Perfil


def test_ver_perfil(como, estudiante):
    datos = como(estudiante).get("/api/auth/perfil/").data
    assert datos["nombre"] == "estudiante"
    assert datos["correo"] == "estudiante@correo.com"
    assert datos["foto_perfil_url"] is None


def test_editar_nombre_correo_y_avatar_predeterminado(como, estudiante):
    respuesta = como(estudiante).patch(
        "/api/auth/perfil/",
        {"nombre": "renombrada", "correo": "nuevo@correo.com", "avatar": "opcionUnoPerfil.png"},
        format="json",
    )
    assert respuesta.status_code == 200
    assert respuesta.data["nombre"] == "renombrada"
    assert respuesta.data["avatar"] == "opcionUnoPerfil.png"


def test_avatar_de_la_biblioteca_es_valido(como, estudiante, administrador, png):
    subido = como(administrador).post(
        "/api/panel/recursos/", {"nombre": "Gato", "archivo": png(), "categoria": "avatar"}, format="multipart"
    )
    assert subido.status_code == 201
    respuesta = como(estudiante).patch("/api/auth/perfil/", {"avatar": subido.data["archivo_url"]}, format="json")
    assert respuesta.status_code == 200, respuesta.data


@pytest.mark.parametrize("datos, campo", [
    ({"nombre": "profesor"}, "nombre"),
    ({"correo": "profesor@correo.com"}, "correo"),
    ({"avatar": "inventado.png"}, "avatar"),
    ({"avatar": "/media/biblioteca/no-existe.png"}, "avatar"),
])
def test_editar_perfil_con_datos_invalidos_responde_400(como, estudiante, profesor, datos, campo):
    respuesta = como(estudiante).patch("/api/auth/perfil/", datos, format="json")
    assert respuesta.status_code == 400
    assert campo in respuesta.data


def test_subir_y_quitar_foto_de_perfil(como, estudiante, png):
    cliente = como(estudiante)
    subida = cliente.patch("/api/auth/perfil/", {"foto_perfil": png("yo.png")}, format="multipart")
    assert subida.status_code == 200
    assert subida.data["foto_perfil_url"].startswith("http")

    quitada = cliente.patch("/api/auth/perfil/", {"foto_perfil": ""}, format="multipart")
    assert quitada.status_code == 200
    assert quitada.data["foto_perfil_url"] is None


# ------------------------------------------------------------------ Contrasenas


def test_cambiar_password(como, api, estudiante):
    respuesta = como(estudiante).post(
        "/api/auth/cambiar-password/",
        {"password_actual": CLAVE, "password_nueva": "OtraClaveSegura9"},
        format="json",
    )
    assert respuesta.status_code == 200
    assert api.post("/api/auth/login/", {"username": "estudiante", "password": "OtraClaveSegura9"}, format="json").status_code == 200


@pytest.mark.parametrize("datos, campo", [
    ({"password_actual": "Incorrecta123", "password_nueva": "OtraClaveSegura9"}, "password_actual"),
    ({"password_actual": CLAVE, "password_nueva": "123"}, "password_nueva"),
    ({"password_actual": CLAVE, "password_nueva": "password"}, "password_nueva"),
])
def test_cambiar_password_invalido_responde_400(como, estudiante, datos, campo):
    respuesta = como(estudiante).post("/api/auth/cambiar-password/", datos, format="json")
    assert respuesta.status_code == 400
    assert campo in respuesta.data


def test_cambiar_password_sin_token_responde_401(api):
    assert api.post("/api/auth/cambiar-password/", {}, format="json").status_code == 401


def test_solicitar_recuperacion_en_debug_devuelve_token(api, estudiante, settings):
    settings.DEBUG = True
    respuesta = api.post("/api/auth/recuperar/solicitar/", {"correo": "estudiante@correo.com"}, format="json")
    assert respuesta.status_code == 200
    assert {"uid", "token"} <= set(respuesta.data["debug"])


def test_solicitar_recuperacion_no_revela_si_el_correo_existe(api, estudiante, settings):
    settings.DEBUG = True
    existe = api.post("/api/auth/recuperar/solicitar/", {"correo": "estudiante@correo.com"}, format="json")
    no_existe = api.post("/api/auth/recuperar/solicitar/", {"correo": "nadie@correo.com"}, format="json")
    assert existe.data["mensaje"] == no_existe.data["mensaje"]
    assert "debug" not in no_existe.data


def test_solicitar_recuperacion_sin_debug_no_expone_token(api, estudiante, settings):
    settings.DEBUG = False
    respuesta = api.post("/api/auth/recuperar/solicitar/", {"correo": "estudiante@correo.com"}, format="json")
    assert respuesta.status_code == 200
    assert "debug" not in respuesta.data


def test_solicitar_recuperacion_con_correo_invalido_responde_400(api):
    assert api.post("/api/auth/recuperar/solicitar/", {"correo": "x"}, format="json").status_code == 400


def _enlace(usuario):
    return {
        "uid": urlsafe_base64_encode(force_bytes(usuario.pk)),
        "token": default_token_generator.make_token(usuario),
    }


def test_confirmar_recuperacion_y_el_token_es_de_un_solo_uso(api, estudiante):
    enlace = _enlace(estudiante)
    datos = {**enlace, "password_nueva": "Recuperada2026"}
    assert api.post("/api/auth/recuperar/confirmar/", datos, format="json").status_code == 200
    assert api.post("/api/auth/login/", {"username": "estudiante", "password": "Recuperada2026"}, format="json").status_code == 200
    # El mismo enlace ya no sirve porque la contrasena cambio.
    assert api.post("/api/auth/recuperar/confirmar/", {**datos, "password_nueva": "OtraMas2026"}, format="json").status_code == 400


@pytest.mark.parametrize("cambio", [
    {"uid": "no-es-base64"},
    {"uid": urlsafe_base64_encode(force_bytes(999999))},
    {"token": "token-falso"},
    {"password_nueva": "123456789"},
])
def test_confirmar_recuperacion_invalida_responde_400(api, estudiante, cambio):
    datos = {**_enlace(estudiante), "password_nueva": "Recuperada2026", **cambio}
    assert api.post("/api/auth/recuperar/confirmar/", datos, format="json").status_code == 400


def test_perfil_se_crea_solo_para_usuarios_del_admin(db):
    usuario = User.objects.create_user("desde_admin", password=CLAVE)
    assert usuario.perfil.avatar == "imgPredeterminadaUsuario.png"
    assert str(usuario.perfil) == "desde_admin"


def test_recurso_visual_str(administrador, como, png):
    como(administrador).post("/api/panel/recursos/", {"nombre": "Insignia", "archivo": png()}, format="multipart")
    assert str(RecursoVisual.objects.get()) == "Insignia"
