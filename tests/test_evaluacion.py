"""Evaluacion por preguntas: flujo completo, reglas de puntaje y limites."""

import pytest

from apps.cursos.models import IntentoEvaluacion, Pregunta, ProgresoUsuario, RecursoVisual

from .conftest import opcion_correcta, opcion_incorrecta

pytestmark = pytest.mark.django_db

BASE = "/api/cursos/abecedario/evaluacion"


def responder(cliente, opcion):
    return cliente.post(f"{BASE}/responder/", {"opcion_id": opcion.id}, format="json")


def test_evaluacion_completa_de_principio_a_fin(como, estudiante, curso):
    cliente = como(estudiante)

    inicio = cliente.post(f"{BASE}/iniciar/")
    assert inicio.status_code == 201
    assert (inicio.data["total"], inicio.data["actual"], inicio.data["finalizado"]) == (3, 1, False)
    # El estudiante nunca recibe cual opcion es la correcta.
    assert all("es_correcta" not in o for o in inicio.data["pregunta"]["opciones"])

    actual = cliente.get(f"{BASE}/actual/")
    assert actual.status_code == 200
    primera = actual.data["pregunta"]["id"]

    # Fallo: suma error y la pregunta sigue activa.
    fallo = responder(cliente, opcion_incorrecta(primera))
    assert fallo.status_code == 200
    assert fallo.data["correcta"] is False
    assert fallo.data["estado"]["pregunta"]["id"] == primera
    assert fallo.data["estado"]["errores"] == 1

    # Acierto tras fallar: avanza, pero no puntua.
    acierto = responder(cliente, opcion_correcta(primera))
    assert acierto.data["correcta"] is True
    assert acierto.data["siguiente"]["actual"] == 2
    assert acierto.data["siguiente"]["aciertos"] == 0

    # Las dos restantes se aciertan a la primera.
    segunda = acierto.data["siguiente"]["pregunta"]["id"]
    tercera = responder(cliente, opcion_correcta(segunda)).data["siguiente"]["pregunta"]["id"]
    final = responder(cliente, opcion_correcta(tercera))

    assert final.data["finalizado"] is True
    resultado = final.data["resultado"]
    assert (resultado["aciertos"], resultado["errores"], resultado["total"]) == (2, 1, 3)
    assert resultado["porcentaje"] == 67
    assert resultado["mensaje"] == "Sigue practicando, vas muy bien."
    assert resultado["detalle_preguntas"][0]["acierto"] is False

    # Queda consolidado en el progreso y en las estrellas.
    progreso = ProgresoUsuario.objects.get(usuario=estudiante, curso=curso)
    assert progreso.completado and not progreso.insignia_100_ganada
    estudiante.perfil.refresh_from_db()
    assert estudiante.perfil.estrellas == 1

    assert cliente.get(f"{BASE}/resultado/").data["aciertos"] == 2
    historial = cliente.get(f"{BASE}/historial/").data
    assert [(h["aciertos"], h["total"]) for h in historial] == [(2, 3)]
    assert cliente.get("/api/progreso/").data[0]["curso_insignia_nombre"] == "Curso completado"


def test_evaluacion_perfecta_gana_insignia_100(como, estudiante, curso, administrador, png):
    subida = como(administrador).post(
        "/api/panel/recursos/", {"nombre": "Oro", "archivo": png(), "categoria": "curso_100"}, format="multipart"
    )
    curso.insignia_100 = RecursoVisual.objects.get(pk=subida.data["id"])
    curso.save()

    cliente = como(estudiante)
    pregunta = cliente.post(f"{BASE}/iniciar/").data["pregunta"]["id"]
    for _ in range(3):
        respuesta = responder(cliente, opcion_correcta(pregunta))
        if not respuesta.data["finalizado"]:
            pregunta = respuesta.data["siguiente"]["pregunta"]["id"]

    resultado = respuesta.data["resultado"]
    assert resultado["porcentaje"] == 100
    assert resultado["mensaje"] == "Excelente trabajo, completaste todo sin errores."
    assert resultado["insignia_100_ganada"] and resultado["insignia_100_nueva"]
    progreso = cliente.get("/api/progreso/").data[0]
    assert progreso["curso_insignia_tipo"] == "curso_100"


def test_responder_sin_evaluacion_iniciada_responde_404(como, estudiante, curso):
    opcion = opcion_correcta(Pregunta.objects.filter(curso=curso).first().id)
    respuesta = responder(como(estudiante), opcion)
    assert respuesta.status_code == 404


def test_responder_con_opcion_de_otra_pregunta_responde_400(como, estudiante, curso):
    cliente = como(estudiante)
    actual = cliente.post(f"{BASE}/iniciar/").data["pregunta"]["id"]
    otra = Pregunta.objects.filter(curso=curso).exclude(pk=actual).first()
    respuesta = responder(cliente, opcion_correcta(otra.id))
    assert respuesta.status_code == 400


def test_responder_sin_opcion_responde_400(como, estudiante, curso):
    cliente = como(estudiante)
    cliente.post(f"{BASE}/iniciar/")
    assert cliente.post(f"{BASE}/responder/", {}, format="json").status_code == 400


def test_pregunta_actual_sin_intento_responde_404(como, estudiante, curso):
    assert como(estudiante).get(f"{BASE}/actual/").status_code == 404


def test_resultado_sin_terminar_ninguna_responde_404(como, estudiante, curso):
    assert como(estudiante).get(f"{BASE}/resultado/").status_code == 404


def test_iniciar_curso_sin_preguntas_responde_404(como, estudiante, crear_curso):
    crear_curso("vacio", preguntas=0)
    assert como(estudiante).post("/api/cursos/vacio/evaluacion/iniciar/").status_code == 404


def test_iniciar_curso_inexistente_responde_404(como, estudiante):
    assert como(estudiante).post("/api/cursos/no-existe/evaluacion/iniciar/").status_code == 404


def test_evaluacion_sin_token_responde_401(api, curso):
    assert api.post(f"{BASE}/iniciar/").status_code == 401


def test_reiniciar_descarta_el_intento_abierto(como, estudiante, curso):
    cliente = como(estudiante)
    cliente.post(f"{BASE}/iniciar/")
    cliente.post(f"{BASE}/iniciar/")
    assert IntentoEvaluacion.objects.filter(usuario=estudiante, finalizado=False).count() == 1


def test_limite_de_preguntas_por_evaluacion(como, estudiante, crear_curso):
    crear_curso("abecedario", preguntas=6, preguntas_por_evaluacion=2)
    assert como(estudiante).post(f"{BASE}/iniciar/").data["total"] == 2


def test_si_borran_una_pregunta_el_intento_se_descarta(como, estudiante, curso):
    cliente = como(estudiante)
    actual = cliente.post(f"{BASE}/iniciar/").data["pregunta"]["id"]
    Pregunta.objects.filter(pk=actual).delete()
    assert cliente.get(f"{BASE}/actual/").status_code == 404
    assert not IntentoEvaluacion.objects.filter(usuario=estudiante).exists()


def test_solo_se_conservan_los_ultimos_cinco_intentos(como, estudiante, crear_curso):
    crear_curso("abecedario", preguntas=1)
    cliente = como(estudiante)
    for _ in range(7):
        pregunta = cliente.post(f"{BASE}/iniciar/").data["pregunta"]["id"]
        responder(cliente, opcion_correcta(pregunta))
    assert IntentoEvaluacion.objects.filter(usuario=estudiante, finalizado=True).count() == 5
    assert len(cliente.get(f"{BASE}/historial/").data) == 5


@pytest.mark.parametrize("errores, mensaje", [
    (0, "Excelente trabajo, completaste todo sin errores."),
    (10, "Sigue practicando, vas muy bien."),
    (20, "La practica hace al maestro."),
    (40, "Echale un vistazo al diccionario."),
])
def test_mensajes_de_retroalimentacion(estudiante, curso, errores, mensaje):
    intento = IntentoEvaluacion(usuario=estudiante, curso=curso, errores=errores)
    assert intento.mensaje_retroalimentacion() == mensaje


def test_representacion_de_modelos(estudiante, curso):
    intento = IntentoEvaluacion.objects.create(usuario=estudiante, curso=curso, orden=[1])
    pregunta = Pregunta.objects.filter(curso=curso).first()
    assert str(curso) == "Abecedario"
    assert str(intento) == "estudiante - abecedario (en curso)"
    assert str(pregunta) == "Abecedario -> Pregunta 1?"
    assert "(Correcta)" in str(pregunta.opciones.get(es_correcta=True))
    assert str(curso.diccionario.first()) == "Palabra 1 - abecedario"
    intento.finalizado = True
    assert intento.pregunta_actual_id() is None
    assert "finalizado" in str(intento)
    assert str(ProgresoUsuario(usuario=estudiante, curso=curso)) == "estudiante -> Abecedario"
