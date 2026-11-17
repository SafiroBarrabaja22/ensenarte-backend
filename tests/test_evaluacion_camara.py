"""
Evaluacion con camara: flujo, rol y token.

Las reglas de calculo (umbral, limites, normalizacion) ya estan cubiertas en
apps/evaluacion_camara/tests.py; aqui va el recorrido completo y los modelos.
"""

import pytest

from apps.evaluacion_camara.models import EvaluacionCamara

pytestmark = pytest.mark.django_db


def intentos(correctas, total):
    return [
        {"letra_objetivo": "ABCDEFGHIJ"[n % 10], "acerto": n < correctas, "tiempo_ms": 1200, "confianza": 0.9}
        for n in range(total)
    ]


def test_sesion_con_camara_completa_con_jwt_real(con_jwt, estudiante, crear_curso):
    crear_curso("abecedario", preguntas=0)
    cliente = con_jwt(estudiante)
    guardada = cliente.post(
        "/api/evaluacion-camara/", {"curso": "abecedario", "intentos": intentos(8, 10)}, format="json"
    )
    assert guardada.status_code == 201
    assert (guardada.data["porcentaje"], guardada.data["aprobado"]) == (80, True)

    historial = cliente.get("/api/evaluacion-camara/?curso=abecedario").data
    assert historial["count"] == 1
    assert cliente.get("/api/progreso/").data[0]["completado"] is True


def test_curso_inexistente_responde_400(como, estudiante):
    respuesta = como(estudiante).post(
        "/api/evaluacion-camara/", {"curso": "no-existe", "intentos": intentos(1, 1)}, format="json"
    )
    assert respuesta.status_code == 400
    assert "curso" in respuesta.data


def test_representacion_de_modelos_de_camara(como, estudiante, crear_curso):
    crear_curso("abecedario", preguntas=0)
    como(estudiante).post("/api/evaluacion-camara/", {"curso": "abecedario", "intentos": intentos(1, 2)}, format="json")
    sesion = EvaluacionCamara.objects.get()
    assert str(sesion) == "estudiante - 1/2 (no aprobada)"
    assert [str(i) for i in sesion.intentos.all()] == ["A (ok)", "B (x)"]
