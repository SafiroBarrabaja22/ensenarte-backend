"""Catalogo publico, detalle, diccionario y progreso."""

import pytest

from apps.cursos.models import PalabraDiccionario

pytestmark = pytest.mark.django_db


def test_catalogo_es_publico_y_solo_muestra_cursos_activos(api, crear_curso):
    crear_curso("abecedario")
    crear_curso("archivado", activo=False)
    respuesta = api.get("/api/cursos/")
    assert respuesta.status_code == 200
    assert [c["nombre"] for c in respuesta.data] == ["abecedario"]
    assert respuesta.data[0]["total_preguntas"] == 3
    assert respuesta.data[0]["total_palabras"] == 2


def test_total_preguntas_respeta_el_limite_por_evaluacion(api, crear_curso):
    crear_curso("abecedario", preguntas=5, preguntas_por_evaluacion=2)
    assert api.get("/api/cursos/abecedario/").data["total_preguntas"] == 2


def test_detalle_de_curso(api, curso):
    respuesta = api.get("/api/cursos/abecedario/")
    assert respuesta.status_code == 200
    assert respuesta.data["titulo"] == "Abecedario"
    assert respuesta.data["insignia_100"] is None


@pytest.mark.parametrize("slug", ["no-existe", "archivado"])
def test_detalle_de_curso_inexistente_o_inactivo_responde_404(api, crear_curso, slug):
    crear_curso("archivado", activo=False)
    assert api.get(f"/api/cursos/{slug}/").status_code == 404


def test_diccionario_en_el_orden_definido(como, estudiante, curso):
    PalabraDiccionario.objects.filter(curso=curso, titulo="Palabra 1").update(orden=9)
    respuesta = como(estudiante).get("/api/cursos/abecedario/diccionario/")
    assert respuesta.status_code == 200
    assert respuesta.data["curso"]["nombre"] == "abecedario"
    assert [p["titulo"] for p in respuesta.data["palabras"]] == ["Palabra 2", "Palabra 1"]


def test_diccionario_sin_token_responde_401(api, curso):
    assert api.get("/api/cursos/abecedario/diccionario/").status_code == 401


def test_diccionario_de_curso_inexistente_responde_404(como, estudiante):
    assert como(estudiante).get("/api/cursos/no-existe/diccionario/").status_code == 404


def test_progreso_vacio_al_empezar(como, estudiante):
    respuesta = como(estudiante).get("/api/progreso/")
    assert respuesta.status_code == 200
    assert respuesta.data == []
