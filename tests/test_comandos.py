"""Comandos de gestion: poblar_datos, exportar_contenido y cargar_contenido."""

import json
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.cursos.management.commands import cargar_contenido, exportar_contenido
from apps.cursos.management.commands.poblar_datos import CLAVE_DEMO, USUARIOS_DEMO
from apps.cursos.models import Curso, IntentoEvaluacion, Pregunta, ProgresoUsuario, RecursoVisual
from apps.usuarios.roles import roles_de

pytestmark = pytest.mark.django_db


def correr(*args, **kwargs):
    salida = StringIO()
    call_command(*args, stdout=salida, **kwargs)
    return salida.getvalue()


# ------------------------------------------------------------------ poblar_datos


def test_poblar_datos_con_debug_crea_una_cuenta_por_rol(settings, api):
    settings.DEBUG = True
    correr("poblar_datos")
    for nombre, _, rol in USUARIOS_DEMO:
        assert rol in roles_de(User.objects.get(username=nombre))
    login = api.post("/api/auth/login/", {"username": "profesor_demo", "password": CLAVE_DEMO}, format="json")
    assert login.status_code == 200
    assert Curso.objects.filter(nombre__in=["abecedario", "saludos"]).count() == 2
    assert Pregunta.objects.filter(curso__nombre="abecedario").count() == 10


def test_poblar_datos_es_idempotente_y_restablece_la_clave(settings):
    settings.DEBUG = True
    correr("poblar_datos")
    usuario = User.objects.get(username="estudiante_demo")
    usuario.set_password("CambiadaPorAlguien1")
    usuario.save()
    salida = correr("poblar_datos")
    assert "restablecido" in salida
    assert User.objects.filter(username="estudiante_demo").count() == 1
    assert User.objects.get(username="estudiante_demo").check_password(CLAVE_DEMO)
    assert Pregunta.objects.filter(curso__nombre="abecedario").count() == 10


def test_poblar_datos_sin_debug_no_crea_cuentas_con_clave_conocida(settings):
    settings.DEBUG = False
    salida = correr("poblar_datos")
    assert "no se crean cuentas" in salida
    assert not User.objects.filter(username="admin_demo").exists()
    assert Curso.objects.exists()


def test_poblar_datos_sin_debug_con_bandera_si_las_crea(settings):
    settings.DEBUG = False
    correr("poblar_datos", "--usuarios-demo")
    assert User.objects.get(username="admin_demo").is_superuser


# ------------------------------------------------------------------ exportar / cargar


@pytest.fixture
def fixture_temporal(tmp_path, monkeypatch):
    """Redirige el JSON compartido a una carpeta temporal (no toca el del repositorio)."""
    ruta = tmp_path / "contenido.json"
    monkeypatch.setattr(exportar_contenido, "RUTA_FIXTURE", ruta)
    monkeypatch.setattr(cargar_contenido, "RUTA_FIXTURE", ruta)
    return ruta


def test_exportar_y_cargar_contenido(fixture_temporal, crear_curso, profesor, estudiante):
    curso = crear_curso("abecedario", creado_por=profesor)
    ProgresoUsuario.objects.create(usuario=estudiante, curso=curso, completado=True)
    salida = correr("exportar_contenido")
    assert "Exportado" in salida

    registros = json.loads(fixture_temporal.read_text(encoding="utf-8"))
    cursos = [r for r in registros if r["model"] == "cursos.curso"]
    assert cursos[0]["fields"]["creado_por"] is None  # los usuarios no se comparten

    Curso.objects.all().delete()
    correr("cargar_contenido", "--si")
    assert Curso.objects.get(nombre="abecedario").preguntas.count() == 3
    assert not ProgresoUsuario.objects.exists()  # el progreso dependia del contenido viejo


def test_cargar_contenido_pide_confirmacion(fixture_temporal, crear_curso, monkeypatch):
    crear_curso("abecedario")
    correr("exportar_contenido")
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert "Cancelado" in correr("cargar_contenido")
    assert Curso.objects.exists()

    monkeypatch.setattr("builtins.input", lambda _: "s")
    assert "Contenido cargado" in correr("cargar_contenido")


def test_cargar_contenido_sin_archivo_falla(fixture_temporal):
    with pytest.raises(CommandError):
        correr("cargar_contenido", "--si")


# ------------------------------------------------------------------ otorgar_insignias_curso_100


@pytest.fixture
def curso_con_insignia(crear_curso):
    curso = crear_curso("abecedario", preguntas=1)
    curso.insignia_100 = RecursoVisual.objects.create(
        nombre="Oro", archivo="biblioteca/oro.png", categoria=RecursoVisual.Categoria.CURSO_100
    )
    curso.save()
    return curso


def test_otorgar_insignia_a_progreso_existente_sin_completar(curso_con_insignia, estudiante):
    ProgresoUsuario.objects.create(usuario=estudiante, curso=curso_con_insignia, completado=False)
    IntentoEvaluacion.objects.create(
        usuario=estudiante, curso=curso_con_insignia, orden=[1], aciertos=1, finalizado=True
    )
    correr("otorgar_insignias_curso_100")
    progreso = ProgresoUsuario.objects.get(usuario=estudiante, curso=curso_con_insignia)
    assert progreso.insignia_100_ganada and progreso.completado
    estudiante.perfil.refresh_from_db()
    assert estudiante.perfil.estrellas == 1


def test_otorgar_insignia_no_cuenta_intentos_imperfectos(curso_con_insignia, estudiante):
    IntentoEvaluacion.objects.create(
        usuario=estudiante, curso=curso_con_insignia, orden=[1, 2], aciertos=1, finalizado=True
    )
    correr("otorgar_insignias_curso_100")
    assert not ProgresoUsuario.objects.exists()
