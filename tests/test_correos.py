"""
Correos con plantilla HTML (apps/correos).

Las pruebas usan el backend de memoria de Django (mailoutbox): nada sale a la
red. Los envios se programan con transaction.on_commit, asi que se ejecutan con
django_capture_on_commit_callbacks(execute=True).
"""

import re
import smtplib

import pytest

from apps.correos import servicio
from apps.correos.servicio import CID_LOGO

from .conftest import CLAVE, opcion_correcta, opcion_incorrecta

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ utilidades


def html_de(correo):
    return next(contenido for contenido, tipo in correo.alternatives if tipo == "text/html")


def logo_incrustado(correo):
    """El logo viaja como parte image/png con Content-ID, no como enlace."""
    for parte in correo.message().walk():
        if parte.get_content_type() == "image/png" and parte["Content-ID"] == f"<{CID_LOGO}>":
            return True
    return False


def cumple_reglas_de_correo(correo):
    html = html_de(correo)
    assert correo.body.strip(), "falta la version en texto plano"
    assert "<style" not in html.lower(), "Gmail elimina las etiquetas <style>"
    assert not re.search(r"display\s*:\s*(flex|grid)", html), "sin flexbox ni grid"
    assert 'role="presentation"' in html and "<table" in html, "maquetacion con tablas"
    assert "max-width:600px" in html and 'width="600"' in html, "ancho maximo 600px"
    assert f'src="cid:{CID_LOGO}"' in html, "logo por Content-ID"
    assert not re.search(r'<img[^>]+src="https?://', html), "sin imagenes remotas"
    assert logo_incrustado(correo)
    return html


def correos_para(mailoutbox, direccion):
    return [correo for correo in mailoutbox if correo.to == [direccion]]


def terminar_evaluacion(cliente, slug="abecedario", fallar_primera=True):
    base = f"/api/cursos/{slug}/evaluacion"
    pregunta = cliente.post(f"{base}/iniciar/").data["pregunta"]["id"]
    if fallar_primera:
        cliente.post(f"{base}/responder/", {"opcion_id": opcion_incorrecta(pregunta).id}, format="json")
    while True:
        respuesta = cliente.post(f"{base}/responder/", {"opcion_id": opcion_correcta(pregunta).id}, format="json")
        if respuesta.data["finalizado"]:
            return respuesta.data["resultado"]
        pregunta = respuesta.data["siguiente"]["pregunta"]["id"]


# ------------------------------------------------------------------ 1. Bienvenida


def test_registro_envia_correo_de_bienvenida(api, mailoutbox, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = api.post(
            "/api/auth/registro/",
            {"nombre": "lucia", "correo": "lucia@correo.com", "password": CLAVE},
            format="json",
        )
    assert respuesta.status_code == 201
    assert len(mailoutbox) == 1
    correo = mailoutbox[0]
    assert correo.to == ["lucia@correo.com"]
    assert correo.subject == "Bienvenid@ a enSEÑArte"

    html = cumple_reglas_de_correo(correo)
    assert "¡Bienvenid@, lucia!" in html
    assert "/pages/cursos-usuario.html" in html
    assert "lucia" in correo.body


def test_el_nombre_del_usuario_se_escapa_en_el_html(crear_usuario, mailoutbox):
    usuario = crear_usuario(nombre="<b>pepe</b>")
    assert servicio.enviar_bienvenida(usuario)
    html = html_de(mailoutbox[0])
    assert "&lt;b&gt;pepe&lt;/b&gt;" in html
    assert "<b>pepe</b>" not in html


# ------------------------------------------------------------------ 2. Resultados


def test_terminar_evaluacion_envia_resultados(como, estudiante, curso, mailoutbox, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        resultado = terminar_evaluacion(como(estudiante))

    enviados = correos_para(mailoutbox, "estudiante@correo.com")
    assert len(enviados) == 1
    correo = enviados[0]
    assert correo.subject == "Tus resultados en Abecedario"

    html = cumple_reglas_de_correo(correo)
    assert (resultado["aciertos"], resultado["errores"]) == (2, 1)
    assert re.search(r">2</div>\s*<div[^>]*>Aciertos<", html)
    assert re.search(r">1</div>\s*<div[^>]*>Errores<", html)
    assert "67%" in html and "de 3 preguntas" in html
    assert resultado["mensaje"] == "Sigue practicando, vas muy bien."
    assert resultado["mensaje"] in html
    assert "/pages/retroalimentacion.html?curso=abecedario" in html
    assert "Aciertos:   2" in correo.body and "Errores:    1" in correo.body


def test_resultados_perfectos_anuncian_la_insignia(estudiante, curso, mailoutbox):
    resultado = {"aciertos": 3, "errores": 0, "total": 3, "porcentaje": 100,
                 "mensaje": "Excelente trabajo, completaste todo sin errores.", "insignia_100_nueva": True}
    assert servicio.enviar_resultados(estudiante, curso, resultado)
    assert "Curso 100 %" in html_de(mailoutbox[0])


# ------------------------------------------------------------------ 3. Aviso al profesor


def test_completar_un_curso_avisa_a_su_profesor(como, estudiante, curso, mailoutbox, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        terminar_evaluacion(como(estudiante))

    avisos = correos_para(mailoutbox, "profesor@correo.com")
    assert len(avisos) == 1
    correo = avisos[0]
    assert correo.subject == "estudiante completó Abecedario"
    html = cumple_reglas_de_correo(correo)
    assert "<strong>estudiante</strong> completó <strong>Abecedario</strong>" in html
    assert "Hola, profesor." in html
    assert "/pages/panel/index.html" in html


def test_el_aviso_solo_se_envia_la_primera_vez(como, estudiante, curso, mailoutbox, django_capture_on_commit_callbacks):
    cliente = como(estudiante)
    with django_capture_on_commit_callbacks(execute=True):
        terminar_evaluacion(cliente)
    with django_capture_on_commit_callbacks(execute=True):
        terminar_evaluacion(cliente, fallar_primera=False)
    assert len(correos_para(mailoutbox, "profesor@correo.com")) == 1
    assert len(correos_para(mailoutbox, "estudiante@correo.com")) == 2  # resultados de cada intento


def test_aprobar_con_camara_tambien_avisa_al_profesor(como, estudiante, curso, mailoutbox, django_capture_on_commit_callbacks):
    intentos = [{"letra_objetivo": "A", "acerto": n < 8, "tiempo_ms": 1000} for n in range(10)]
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = como(estudiante).post(
            "/api/evaluacion-camara/", {"curso": "abecedario", "intentos": intentos}, format="json"
        )
    assert respuesta.data["aprobado"] is True
    assert len(correos_para(mailoutbox, "profesor@correo.com")) == 1


def test_el_profesor_no_se_avisa_a_si_mismo(profesor, curso, mailoutbox):
    # Un Profesor ya no hace cursos (solo el Estudiante), pero el aviso sigue
    # protegido por si la cuenta del dueno aparece como quien completo el curso.
    assert servicio.avisar_curso_completado(curso, profesor) is False
    assert mailoutbox == []


def test_curso_sin_profesor_no_envia_aviso(estudiante, crear_curso, mailoutbox):
    assert servicio.avisar_curso_completado(crear_curso("huerfano", creado_por=None), estudiante) is False
    assert servicio.avisar_curso_completado(None, estudiante) is False
    assert mailoutbox == []


# ------------------------------------------------------------------ Fallos


def test_un_fallo_de_smtp_no_tumba_el_registro(api, monkeypatch, caplog, django_capture_on_commit_callbacks):
    def smtp_caido(self, fail_silently=False):
        raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    monkeypatch.setattr(servicio.CorreoConLogo, "send", smtp_caido)
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = api.post(
            "/api/auth/registro/",
            {"nombre": "sin_correo", "correo": "x@correo.com", "password": CLAVE},
            format="json",
        )
    assert respuesta.status_code == 201
    assert api.post("/api/auth/login/", {"username": "sin_correo", "password": CLAVE}, format="json").status_code == 200
    assert "No se pudo enviar el correo" in caplog.text


def test_un_error_al_preparar_el_correo_no_se_propaga(estudiante, monkeypatch, caplog, mailoutbox):
    def plantilla_rota(*args, **kwargs):
        raise RuntimeError("plantilla rota")

    monkeypatch.setattr(servicio, "render_to_string", plantilla_rota)
    assert servicio.enviar_bienvenida(estudiante) is False
    assert mailoutbox == []
    assert "Fallo al preparar el correo enviar_bienvenida" in caplog.text


def test_usuario_sin_correo_no_recibe_nada(crear_usuario, mailoutbox):
    usuario = crear_usuario(nombre="anonimo")
    usuario.email = ""
    assert servicio.enviar_bienvenida(usuario) is False
    assert servicio.enviar_resultados(usuario, None, {}) is False
    assert mailoutbox == []
