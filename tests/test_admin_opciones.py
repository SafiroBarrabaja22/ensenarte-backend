"""
Inline de opciones en el admin de Django (apps/cursos/admin.py).

- El formset rechaza mas de una correcta y mas del maximo de opciones con el
  error normal del admin (200 con el formulario), no con un 500.
- Los cambios validos (cambiar la correcta, borrar la correcta y marcar otra)
  se guardan en un orden que los triggers de MySQL aceptan. En SQLite estas
  pruebas verifican el resultado; en MySQL ademas demuestran que el trigger
  opcion_una_correcta_update no salta.
"""

import pytest

from apps.cursos.models import MAXIMO_OPCIONES_POR_PREGUNTA, OpcionPregunta, Pregunta

pytestmark = pytest.mark.django_db

PREFIJO = "opciones"


@pytest.fixture
def pregunta(crear_curso):
    """Pregunta con 4 opciones A0..D0; la correcta es A0."""
    return Pregunta.objects.filter(curso=crear_curso("admin", preguntas=1, palabras=0)).get()


def url_de(pregunta):
    return f"/admin/cursos/pregunta/{pregunta.id}/change/"


def formulario(pregunta, cambios=None, borrar=(), nuevas=()):
    """
    POST del admin de la pregunta. `cambios`: {texto_opcion: es_correcta} para
    las existentes (las demas conservan su valor); `borrar`: textos a borrar;
    `nuevas`: [(texto, es_correcta)].
    """
    cambios = cambios or {}
    existentes = list(pregunta.opciones.order_by("id"))
    datos = {
        "curso": pregunta.curso_id, "texto": pregunta.texto, "video": pregunta.video or "",
        f"{PREFIJO}-TOTAL_FORMS": len(existentes) + len(nuevas),
        f"{PREFIJO}-INITIAL_FORMS": len(existentes),
        f"{PREFIJO}-MIN_NUM_FORMS": 0,
        f"{PREFIJO}-MAX_NUM_FORMS": MAXIMO_OPCIONES_POR_PREGUNTA,
        "_save": "Guardar",
    }
    for i, opcion in enumerate(existentes):
        datos[f"{PREFIJO}-{i}-id"] = opcion.id
        datos[f"{PREFIJO}-{i}-pregunta"] = pregunta.id
        datos[f"{PREFIJO}-{i}-texto"] = opcion.texto
        if cambios.get(opcion.texto, opcion.es_correcta):
            datos[f"{PREFIJO}-{i}-es_correcta"] = "on"
        if opcion.texto in borrar:
            datos[f"{PREFIJO}-{i}-DELETE"] = "on"
    for j, (texto, correcta) in enumerate(nuevas, start=len(existentes)):
        datos[f"{PREFIJO}-{j}-pregunta"] = pregunta.id
        datos[f"{PREFIJO}-{j}-texto"] = texto
        if correcta:
            datos[f"{PREFIJO}-{j}-es_correcta"] = "on"
    return datos


def correctas(pregunta):
    return list(pregunta.opciones.filter(es_correcta=True).values_list("texto", flat=True))


# ------------------------------------------------------------------ Validacion


def test_dos_correctas_muestra_error_de_validacion(admin_client, pregunta):
    respuesta = admin_client.post(url_de(pregunta), formulario(pregunta, cambios={"B0": True}))
    assert respuesta.status_code == 200          # el formulario se vuelve a mostrar, no un 500
    assert "Solo una opción puede ser la correcta y marcaste 2." in respuesta.content.decode()
    assert correctas(pregunta) == ["A0"]          # nada se guardo


def test_dos_correctas_nuevas_tambien_se_rechazan(admin_client, crear_curso):
    pregunta = Pregunta.objects.create(curso=crear_curso("vacia", preguntas=0, palabras=0), texto="¿Nueva?")
    respuesta = admin_client.post(url_de(pregunta), formulario(pregunta, nuevas=[("X", True), ("Y", True)]))
    assert respuesta.status_code == 200
    assert "Solo una opción puede ser la correcta" in respuesta.content.decode()
    assert not pregunta.opciones.exists()


def test_quinta_opcion_muestra_error_de_validacion(admin_client, pregunta):
    respuesta = admin_client.post(url_de(pregunta), formulario(pregunta, nuevas=[("E0", False)]))
    assert respuesta.status_code == 200
    assert f"Una pregunta admite como máximo {MAXIMO_OPCIONES_POR_PREGUNTA} opciones; hay 5." in respuesta.content.decode()
    assert pregunta.opciones.count() == MAXIMO_OPCIONES_POR_PREGUNTA


def test_borrar_una_y_agregar_otra_no_excede_el_maximo(admin_client, pregunta):
    respuesta = admin_client.post(url_de(pregunta), formulario(pregunta, borrar={"D0"}, nuevas=[("E0", False)]))
    assert respuesta.status_code == 302
    assert sorted(pregunta.opciones.values_list("texto", flat=True)) == ["A0", "B0", "C0", "E0"]


# ------------------------------------------------------------------ Cambios validos


def test_cambiar_la_correcta_a_una_opcion_anterior(admin_client, pregunta):
    """De D0 a A0: si se guardara en orden de id, A0 se marcaria antes de desmarcar D0."""
    OpcionPregunta.objects.filter(pregunta=pregunta).update(es_correcta=False)
    OpcionPregunta.objects.filter(pregunta=pregunta, texto="D0").update(es_correcta=True)
    respuesta = admin_client.post(url_de(pregunta), formulario(pregunta, cambios={"A0": True, "D0": False}))
    assert respuesta.status_code == 302
    assert correctas(pregunta) == ["A0"]


def test_cambiar_la_correcta_a_una_opcion_posterior(admin_client, pregunta):
    respuesta = admin_client.post(url_de(pregunta), formulario(pregunta, cambios={"A0": False, "C0": True}))
    assert respuesta.status_code == 302
    assert correctas(pregunta) == ["C0"]


def test_borrar_la_correcta_y_marcar_otra(admin_client, pregunta):
    respuesta = admin_client.post(url_de(pregunta), formulario(pregunta, cambios={"B0": True}, borrar={"A0"}))
    assert respuesta.status_code == 302
    assert correctas(pregunta) == ["B0"]
    assert not pregunta.opciones.filter(texto="A0").exists()


def test_nueva_opcion_correcta_reemplaza_a_la_anterior(admin_client, pregunta):
    respuesta = admin_client.post(url_de(pregunta), formulario(pregunta, cambios={"A0": False}, borrar={"D0"},
                                                              nuevas=[("Nueva", True)]))
    assert respuesta.status_code == 302
    assert correctas(pregunta) == ["Nueva"]


def test_las_filas_vacias_no_cuentan(admin_client, crear_curso):
    pregunta = Pregunta.objects.create(curso=crear_curso("parcial", preguntas=0, palabras=0), texto="¿Dos?")
    datos = formulario(pregunta, nuevas=[("X", True), ("Y", False)])
    datos[f"{PREFIJO}-TOTAL_FORMS"] = MAXIMO_OPCIONES_POR_PREGUNTA   # dos filas extra en blanco
    respuesta = admin_client.post(url_de(pregunta), datos)
    assert respuesta.status_code == 302
    assert pregunta.opciones.count() == 2
