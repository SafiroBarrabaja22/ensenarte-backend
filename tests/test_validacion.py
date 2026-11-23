"""
Rol Validador: revisa las senas (gifs de la biblioteca) que sube el Interprete.

Reglas en apps/cursos/validacion.py: una sena nueva o reemplazada queda
pendiente, solo el Validador la aprueba o rechaza (con comentario), el
Profesor solo ve y usa senas aprobadas, y el diccionario de los estudiantes
oculta las palabras cuya sena no esta aprobada.
"""

import pytest

from apps.cursos.models import RecursoVisual, RevisionSena
from apps.usuarios.roles import ROL_VALIDADOR
from config.limites import MAX_COMENTARIO_VALIDACION

pytestmark = pytest.mark.django_db

RECURSOS = "/api/panel/recursos/"


@pytest.fixture
def subir(como, interprete, gif, png):
    """subir(tipo="gif", categoria="recurso") -> datos del recurso que sube el Interprete."""
    def _subir(tipo="gif", categoria="recurso", nombre="Seña A"):
        archivo = gif() if tipo == "gif" else png()
        respuesta = como(interprete).post(
            RECURSOS, {"nombre": nombre, "archivo": archivo, "categoria": categoria}, format="multipart"
        )
        assert respuesta.status_code == 201, respuesta.data
        return respuesta.data
    return _subir


def validar(cliente, recurso_id, decision, comentario=""):
    return cliente.post(
        f"{RECURSOS}{recurso_id}/validar/", {"decision": decision, "comentario": comentario}, format="json"
    )


def ids_visibles(cliente, **filtros):
    respuesta = cliente.get(RECURSOS, filtros)
    assert respuesta.status_code == 200
    return {recurso["id"] for recurso in respuesta.data}


# ------------------------------------------------------------------ Rol


def test_el_validador_tiene_su_rol_y_puede_aprender(como, validador):
    cliente = como(validador)
    assert ROL_VALIDADOR in cliente.get("/api/auth/perfil/").data["roles"]
    assert cliente.get("/api/progreso/").status_code == 200


# ------------------------------------------------------------------ Estado inicial


def test_un_gif_de_sena_nuevo_queda_pendiente(subir):
    sena = subir()
    assert sena["es_sena"] is True
    assert sena["estado_validacion"] == "pendiente"
    assert sena["subido_por"] == "interprete"


@pytest.mark.parametrize("tipo, categoria", [("png", "recurso"), ("gif", "avatar"), ("png", "insignia")])
def test_lo_que_no_es_sena_no_pasa_por_el_validador(subir, tipo, categoria):
    recurso = subir(tipo, categoria)
    assert recurso["es_sena"] is False
    assert recurso["estado_validacion"] == "aprobada"


def test_lo_que_ya_existia_queda_aprobado(db):
    """El valor por defecto de la columna (lo que recibieron los recursos existentes)."""
    campo = RecursoVisual._meta.get_field("estado_validacion")
    assert campo.default == RecursoVisual.EstadoValidacion.APROBADA


def test_el_estado_no_se_cambia_editando_el_recurso(como, interprete, administrador, subir):
    sena = subir()
    for usuario in (interprete, administrador):
        como(usuario).patch(f"{RECURSOS}{sena['id']}/", {"estado_validacion": "aprobada"}, format="json")
    assert RecursoVisual.objects.get(pk=sena["id"]).estado_validacion == "pendiente"


# ------------------------------------------------------------------ Quien decide


def test_solo_el_validador_aprueba_o_rechaza(
    como, subir, interprete, administrador, profesor, creador, estudiante, crear_usuario
):
    sena = subir()
    superusuario = crear_usuario(None, "root", is_superuser=True, is_staff=True)
    for usuario in (interprete, administrador, profesor, creador, estudiante, superusuario):
        assert validar(como(usuario), sena["id"], "aprobar").status_code == 403, usuario.username
    assert RecursoVisual.objects.get(pk=sena["id"]).estado_validacion == "pendiente"


def test_el_validador_aprueba(como, validador, subir):
    sena = subir()
    respuesta = validar(como(validador), sena["id"], "aprobar", "Bien hecha.")
    assert respuesta.status_code == 200
    assert respuesta.data["estado_validacion"] == "aprobada"
    assert respuesta.data["comentario_validacion"] == "Bien hecha."
    revision = RevisionSena.objects.get(recurso_id=sena["id"])
    assert (revision.accion, revision.usuario.username) == ("aprobada", "validador")


def test_rechazar_exige_comentario(como, validador, subir):
    sena = subir()
    respuesta = validar(como(validador), sena["id"], "rechazar", "   ")
    assert respuesta.status_code == 400
    assert "comentario" in respuesta.data["detail"]
    respuesta = validar(como(validador), sena["id"], "rechazar", "La mano va a la altura del pecho.")
    assert respuesta.status_code == 200
    assert respuesta.data["estado_validacion"] == "rechazada"
    assert respuesta.data["comentario_validacion"] == "La mano va a la altura del pecho."


@pytest.mark.parametrize("decision, comentario", [
    ("", ""), ("borrar", "x"), ("aprobar", "x" * (MAX_COMENTARIO_VALIDACION + 1)),
])
def test_decision_invalida_responde_400(como, validador, subir, decision, comentario):
    sena = subir()
    assert validar(como(validador), sena["id"], decision, comentario).status_code == 400
    assert RecursoVisual.objects.get(pk=sena["id"]).estado_validacion == "pendiente"


def test_un_recurso_que_no_es_sena_no_se_valida(como, validador, subir):
    imagen = subir("png")
    assert validar(como(validador), imagen["id"], "aprobar").status_code == 400


# ------------------------------------------------------------------ Historial y reenvio


def test_reemplazar_el_archivo_vuelve_a_revision_y_conserva_el_comentario(como, validador, interprete, subir, gif):
    sena = subir()
    validar(como(validador), sena["id"], "rechazar", "Muy rápida.")
    respuesta = como(interprete).patch(f"{RECURSOS}{sena['id']}/", {"archivo": gif()}, format="multipart")
    assert respuesta.status_code == 200
    assert respuesta.data["estado_validacion"] == "pendiente"
    # El comentario de la ultima decision sigue a la vista del Interprete.
    assert respuesta.data["comentario_validacion"] == "Muy rápida."

    historial = como(interprete).get(f"{RECURSOS}{sena['id']}/revisiones/").data
    assert [h["accion"] for h in historial] == ["reenviada", "rechazada"]
    assert historial[1]["comentario"] == "Muy rápida."
    assert historial[0]["archivo"] != historial[1]["archivo"]


def test_cambiar_solo_el_nombre_no_vuelve_a_revision(como, validador, interprete, subir):
    sena = subir()
    validar(como(validador), sena["id"], "aprobar")
    respuesta = como(interprete).patch(f"{RECURSOS}{sena['id']}/", {"nombre": "Seña A (v2)"}, format="json")
    assert respuesta.data["estado_validacion"] == "aprobada"


@pytest.mark.parametrize("rol, esperado", [
    ("validador", 200), ("interprete", 200), ("administrador", 200),
    ("profesor", 403), ("creador", 403), ("estudiante", 403),
])
def test_quien_ve_el_historial(request, como, subir, rol, esperado):
    sena = subir()
    usuario = request.getfixturevalue(rol)
    assert como(usuario).get(f"{RECURSOS}{sena['id']}/revisiones/").status_code == esperado


# ------------------------------------------------------------------ Quien ve las senas sin aprobar


def test_al_profesor_no_le_llegan_senas_sin_aprobar(como, validador, subir, profesor, creador):
    pendiente = subir(nombre="Pendiente")
    rechazada = subir(nombre="Rechazada")
    aprobada = subir(nombre="Aprobada")
    validar(como(validador), rechazada["id"], "rechazar", "No.")
    validar(como(validador), aprobada["id"], "aprobar")
    for usuario in (profesor, creador):
        visibles = ids_visibles(como(usuario), extension="gif", categoria="recurso")
        assert visibles == {aprobada["id"]}, usuario.username
        assert como(usuario).get(f"{RECURSOS}{pendiente['id']}/").status_code == 404


def test_interprete_validador_y_admin_ven_todas_y_filtran_por_estado(
    como, validador, subir, interprete, administrador
):
    pendiente = subir()
    aprobada = subir()
    validar(como(validador), aprobada["id"], "aprobar")
    for usuario in (interprete, validador, administrador):
        assert {pendiente["id"], aprobada["id"]} <= ids_visibles(como(usuario))
        assert ids_visibles(como(usuario), estado="pendiente") == {pendiente["id"]}


# ------------------------------------------------------------------ Uso en palabras y preguntas


def test_solo_se_puede_asignar_una_sena_aprobada(como, validador, subir, profesor, curso):
    palabra = curso.diccionario.first()
    sena = subir()
    cliente = como(profesor)
    url = f"/api/panel/diccionario/{palabra.id}/"

    respuesta = cliente.patch(url, {"video_gif": sena["archivo_url"]}, format="json")
    assert respuesta.status_code == 400
    assert "Validador" in str(respuesta.data["video_gif"])

    validar(como(validador), sena["id"], "aprobar")
    respuesta = cliente.patch(url, {"video_gif": sena["archivo_url"]}, format="json")
    assert respuesta.status_code == 200
    assert respuesta.data["estado_sena"] == "aprobada"


def test_la_pregunta_tambien_exige_sena_aprobada(como, subir, profesor, curso):
    pregunta = curso.preguntas.first()
    sena = subir()
    respuesta = como(profesor).patch(
        f"/api/panel/preguntas/{pregunta.id}/", {"video": sena["archivo_url"]}, format="json"
    )
    assert respuesta.status_code == 400


@pytest.mark.parametrize("valor, esperado", [
    ("/media/contenido/suelto.gif", 400),   # gif subido fuera de la biblioteca
    ("abecedario/b.gif", 200),             # gif de assets/ del frontend (versionado)
    ("", 200),
])
def test_gifs_fuera_de_la_biblioteca(como, profesor, curso, valor, esperado):
    pregunta = curso.preguntas.first()
    respuesta = como(profesor).patch(f"/api/panel/preguntas/{pregunta.id}/", {"video": valor}, format="json")
    assert respuesta.status_code == esperado


def test_reemplazar_la_sena_no_cambia_lo_que_ya_ven_los_estudiantes(
    como, validador, interprete, subir, gif, profesor, estudiante, curso
):
    """
    La palabra guarda la ruta del gif que se aprobo. Si el Interprete reemplaza el
    archivo, la palabra conserva el gif aprobado (sigue visible y editable) y el
    archivo nuevo espera al Validador antes de poder asignarse.
    """
    palabra = curso.diccionario.first()
    sena = subir()
    validar(como(validador), sena["id"], "aprobar")
    como(profesor).patch(f"/api/panel/diccionario/{palabra.id}/", {"video_gif": sena["archivo_url"]}, format="json")

    como(interprete).patch(f"{RECURSOS}{sena['id']}/", {"archivo": gif()}, format="multipart")
    archivo_nuevo = como(interprete).get(f"{RECURSOS}{sena['id']}/").data["archivo_url"]
    assert archivo_nuevo != sena["archivo_url"]

    url = f"/api/panel/diccionario/{palabra.id}/"
    assert como(profesor).patch(url, {"titulo": "Hola"}, format="json").status_code == 200
    assert como(profesor).patch(url, {"video_gif": archivo_nuevo}, format="json").status_code == 400
    datos = como(estudiante).get(f"/api/cursos/{curso.nombre}/diccionario/").data
    assert "Hola" in {p["titulo"] for p in datos["palabras"]}


def test_el_panel_muestra_el_estado_de_la_sena(como, validador, subir, profesor, curso):
    palabra = curso.diccionario.first()
    sena = subir()
    validar(como(validador), sena["id"], "aprobar")
    como(profesor).patch(f"/api/panel/diccionario/{palabra.id}/", {"video_gif": sena["archivo_url"]}, format="json")
    validar(como(validador), sena["id"], "rechazar", "Revisar el movimiento.")

    palabras = como(profesor).get("/api/panel/diccionario/", {"curso": curso.id}).data
    estados = {p["id"]: p["estado_sena"] for p in palabras}
    assert estados[palabra.id] == "rechazada"
    assert set(estados.values()) == {"rechazada", "aprobada"}


# ------------------------------------------------------------------ Diccionario de los estudiantes


def test_el_estudiante_no_ve_palabras_con_sena_sin_aprobar(como, validador, subir, estudiante, curso):
    palabra = curso.diccionario.first()
    sena = subir()
    validar(como(validador), sena["id"], "aprobar")
    palabra.video_gif = sena["archivo_url"]
    palabra.save()

    def titulos():
        datos = como(estudiante).get(f"/api/cursos/{curso.nombre}/diccionario/").data
        return {p["titulo"] for p in datos["palabras"]}

    assert palabra.titulo in titulos()
    validar(como(validador), sena["id"], "rechazar", "Corregir.")
    assert palabra.titulo not in titulos()
    assert len(titulos()) == curso.diccionario.count() - 1
    validar(como(validador), sena["id"], "aprobar")
    assert palabra.titulo in titulos()


def test_subir_gif_directo_a_una_palabra_la_deja_pendiente(como, interprete, estudiante, curso, gif):
    palabra = curso.diccionario.first()
    respuesta = como(interprete).post(f"/api/panel/diccionario/{palabra.id}/gif/", {"gif": gif()}, format="multipart")
    assert respuesta.status_code == 200
    recurso = RecursoVisual.objects.get(archivo=respuesta.data["video_gif"].removeprefix("/media/"))
    assert (recurso.estado_validacion, recurso.subido_por.username) == ("pendiente", "interprete")
    datos = como(estudiante).get(f"/api/cursos/{curso.nombre}/diccionario/").data
    assert palabra.titulo not in {p["titulo"] for p in datos["palabras"]}
