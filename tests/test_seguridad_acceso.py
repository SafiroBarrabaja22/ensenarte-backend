"""
Seguridad de inicio de sesion, registro y recuperacion de contrasena
(apps/usuarios/seguridad.py; docs/SEGURIDAD.md, seccion 8).
"""

import re

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from .conftest import CLAVE
from .test_correos import cumple_reglas_de_correo

pytestmark = pytest.mark.django_db

LOGIN = "/api/auth/login/"
REGISTRO = "/api/auth/registro/"
SOLICITAR = "/api/auth/recuperar/solicitar/"
CONFIRMAR = "/api/auth/recuperar/confirmar/"
NUEVA = "NuevaClave2026!"


def login(api, usuario, clave):
    return api.post(LOGIN, {"username": usuario, "password": clave}, format="json")


def enlace_de(correo):
    """uid y token del enlace del correo de recuperacion (van en el fragmento #)."""
    coincidencia = re.search(r"/pages/recuperar\.html#uid=([\w-]+)&token=([\w-]+)", correo.body)
    assert coincidencia, correo.body
    return coincidencia.group(1), coincidencia.group(2)


# ------------------------------------------------------------------ Bloqueo de cuenta


@override_settings(LOGIN_MAX_FALLOS=5)
def test_cinco_fallos_bloquean_la_cuenta_aunque_luego_acierte(api, estudiante):
    for _ in range(5):
        assert login(api, "estudiante", "incorrecta").status_code == 401
    respuesta = login(api, "estudiante", CLAVE)
    assert respuesta.status_code == 429
    assert "access" not in respuesta.data
    assert "Demasiados intentos fallidos" in respuesta.data["detail"]


@override_settings(LOGIN_MAX_FALLOS=5)
def test_el_bloqueo_es_por_cuenta_no_afecta_a_otros(api, estudiante, profesor):
    for _ in range(5):
        login(api, "estudiante", "incorrecta")
    assert login(api, "profesor", CLAVE).status_code == 200


@override_settings(LOGIN_MAX_FALLOS=5)
def test_el_bloqueo_no_distingue_mayusculas(api, estudiante):
    for _ in range(5):
        login(api, "ESTUDIANTE", "incorrecta")
    assert login(api, "estudiante", CLAVE).status_code == 429


@override_settings(LOGIN_MAX_FALLOS=5)
def test_un_login_correcto_reinicia_el_contador(api, estudiante):
    for _ in range(4):
        login(api, "estudiante", "incorrecta")
    assert login(api, "estudiante", CLAVE).status_code == 200
    for _ in range(4):
        login(api, "estudiante", "incorrecta")
    assert login(api, "estudiante", CLAVE).status_code == 200


@override_settings(LOGIN_MAX_FALLOS=5)
def test_usuario_inexistente_se_bloquea_igual(api):
    """Si solo se bloquearan cuentas reales, el 429 revelaria cuales existen."""
    for _ in range(5):
        assert login(api, "fantasma", "x").status_code == 401
    assert login(api, "fantasma", "x").status_code == 429


@override_settings(LOGIN_MAX_FALLOS=5)
def test_recuperar_la_contrasena_desbloquea_la_cuenta(api, estudiante, mailoutbox):
    for _ in range(5):
        login(api, "estudiante", "incorrecta")
    api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json")
    uid, token = enlace_de(mailoutbox[-1])
    assert api.post(CONFIRMAR, {"uid": uid, "token": token, "password_nueva": NUEVA}, format="json").status_code == 200
    assert login(api, "estudiante", NUEVA).status_code == 200


# ------------------------------------------------------------------ Limite por IP


@pytest.fixture
def limites(monkeypatch):
    """limites(login="3/min") -> tasas mas bajas solo para esta prueba (DRF las lee al importar)."""
    def _limites(**tasas):
        monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {**ScopedRateThrottle.THROTTLE_RATES, **tasas})
    return _limites


@override_settings(LOGIN_MAX_FALLOS=1000)
def test_limite_de_logins_por_ip(api, estudiante, limites):
    limites(login="3/min")
    for _ in range(3):
        login(api, "estudiante", "incorrecta")
    respuesta = login(api, "estudiante", CLAVE)
    assert respuesta.status_code == 429
    assert "Demasiados intentos desde tu conexión" in respuesta.data["detail"]
    assert "Retry-After" in respuesta


def test_limite_de_registros_por_ip(api, limites):
    limites(registro="2/hour")
    for i in range(2):
        datos = {"nombre": f"bot{i}", "correo": f"bot{i}@correo.com", "password": NUEVA}
        assert api.post(REGISTRO, datos, format="json").status_code == 201
    datos = {"nombre": "bot9", "correo": "bot9@correo.com", "password": NUEVA}
    assert api.post(REGISTRO, datos, format="json").status_code == 429
    assert not User.objects.filter(username="bot9").exists()


def test_limite_de_recuperaciones_por_ip(api, limites):
    limites(recuperar_solicitar="2/hour")
    for i in range(2):
        api.post(SOLICITAR, {"correo": f"c{i}@correo.com"}, format="json")
    assert api.post(SOLICITAR, {"correo": "c9@correo.com"}, format="json").status_code == 429


@override_settings(LOGIN_MAX_FALLOS=1000)
def test_inventar_x_forwarded_for_no_evita_el_limite(api, limites, settings):
    """Con NUM_PROXIES=0 (desarrollo) la cabecera se ignora: inventarla no da otra IP."""
    limites(login="2/min")
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}
    for i in range(2):
        api.post(LOGIN, {"username": "x", "password": "y"}, format="json", HTTP_X_FORWARDED_FOR=f"10.0.0.{i}")
    respuesta = api.post(LOGIN, {"username": "x", "password": "y"}, format="json", HTTP_X_FORWARDED_FOR="10.0.0.99")
    assert respuesta.status_code == 429


@override_settings(LOGIN_MAX_FALLOS=1000)
def test_detras_de_funnel_cuenta_la_ip_real_del_cliente(api, limites, settings):
    """
    Con NUM_PROXIES=1 (produccion) cuenta la ultima IP de X-Forwarded-For, la
    que agrega Tailscale Funnel. Lo que el cliente invente delante no cambia nada.
    """
    limites(login="2/min")
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    for i in range(2):
        api.post(LOGIN, {"username": "x", "password": "y"}, format="json",
                 HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, 203.0.113.7")
    misma_ip = api.post(LOGIN, {"username": "x", "password": "y"}, format="json",
                        HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7")
    assert misma_ip.status_code == 429
    otra_ip = api.post(LOGIN, {"username": "x", "password": "y"}, format="json",
                       HTTP_X_FORWARDED_FOR="198.51.100.20")
    assert otra_ip.status_code == 401


# ------------------------------------------------------------------ Trampa para bots


def test_registro_con_el_campo_trampa_lleno_se_rechaza(api):
    datos = {"nombre": "robot", "correo": "robot@correo.com", "password": NUEVA, "sitio_web": "http://spam.example"}
    respuesta = api.post(REGISTRO, datos, format="json")
    assert respuesta.status_code == 400
    assert "No se pudo completar el registro." in str(respuesta.data)
    assert not User.objects.filter(username="robot").exists()


def test_registro_con_el_campo_trampa_vacio_funciona(api):
    datos = {"nombre": "persona", "correo": "persona@correo.com", "password": NUEVA, "sitio_web": ""}
    assert api.post(REGISTRO, datos, format="json").status_code == 201


def test_el_registro_no_permite_elegir_rol_ni_ser_admin(api):
    datos = {"nombre": "listo", "correo": "listo@correo.com", "password": NUEVA,
             "roles": ["Administrador"], "is_staff": True, "is_superuser": True}
    respuesta = api.post(REGISTRO, datos, format="json")
    assert respuesta.status_code == 201
    usuario = User.objects.get(username="listo")
    assert not usuario.is_staff and not usuario.is_superuser
    assert respuesta.data["usuario"]["roles"] == ["Estudiante"]


# ------------------------------------------------------------------ Recuperacion por correo


def test_recuperacion_envia_un_correo_con_enlace_de_confirmacion(api, estudiante, mailoutbox):
    respuesta = api.post(SOLICITAR, {"correo": "Estudiante@Correo.com"}, format="json")
    assert respuesta.status_code == 200
    assert len(mailoutbox) == 1
    correo = mailoutbox[0]
    assert correo.to == ["estudiante@correo.com"]
    assert correo.subject == "Restablece tu contraseña de enSEÑArte"
    html = cumple_reglas_de_correo(correo)
    assert "Sí, fui yo" in html
    assert "Si no fuiste tú" in html and "no cambia" in html
    assert "vence en <strong>60 minutos</strong>" in html
    enlace_de(correo)
    assert CLAVE not in correo.body and CLAVE not in html


def test_el_enlace_permite_restablecer_y_sirve_una_sola_vez(api, estudiante, mailoutbox):
    api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json")
    uid, token = enlace_de(mailoutbox[0])
    datos = {"uid": uid, "token": token, "password_nueva": NUEVA}
    assert api.post(CONFIRMAR, datos, format="json").status_code == 200
    assert login(api, "estudiante", NUEVA).status_code == 200
    assert login(api, "estudiante", CLAVE).status_code == 401
    segunda = api.post(CONFIRMAR, {**datos, "password_nueva": "OtraMas2026!"}, format="json")
    assert segunda.status_code == 400


def test_restablecer_avisa_por_correo_y_cierra_las_sesiones(api, estudiante, mailoutbox,
                                                           django_capture_on_commit_callbacks):
    sesion = login(api, "estudiante", CLAVE).data
    api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json")
    uid, token = enlace_de(mailoutbox[0])
    with django_capture_on_commit_callbacks(execute=True):
        api.post(CONFIRMAR, {"uid": uid, "token": token, "password_nueva": NUEVA}, format="json")

    aviso = mailoutbox[-1]
    assert aviso.subject == "Tu contraseña de enSEÑArte cambió"
    html = cumple_reglas_de_correo(aviso)
    assert "usando un enlace de recuperación" in html
    assert NUEVA not in aviso.body and NUEVA not in html
    # La sesion abierta antes ya no se puede renovar.
    assert api.post("/api/auth/refresh/", {"refresh": sesion["refresh"]}, format="json").status_code == 401


@override_settings(PASSWORD_RESET_TIMEOUT=-1)
def test_un_enlace_vencido_no_sirve(api, estudiante, mailoutbox):
    api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json")
    uid, token = enlace_de(mailoutbox[0])
    respuesta = api.post(CONFIRMAR, {"uid": uid, "token": token, "password_nueva": NUEVA}, format="json")
    assert respuesta.status_code == 400
    assert "expiro o ya fue usado" in str(respuesta.data)


def test_un_token_inventado_no_sirve(api, estudiante, mailoutbox):
    api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json")
    uid, _ = enlace_de(mailoutbox[0])
    respuesta = api.post(CONFIRMAR, {"uid": uid, "token": "abc-123", "password_nueva": NUEVA}, format="json")
    assert respuesta.status_code == 400


def test_correo_sin_cuenta_recibe_aviso_y_la_respuesta_es_igual(api, estudiante, mailoutbox):
    """Siempre llega un correo; la API responde igual, sin revelar quien esta registrado."""
    existe = api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json")
    no_existe = api.post(SOLICITAR, {"correo": "nadie@correo.com"}, format="json")
    assert existe.status_code == no_existe.status_code == 200
    assert existe.data == no_existe.data
    assert [c.to for c in mailoutbox] == [["estudiante@correo.com"], ["nadie@correo.com"]]
    aviso = mailoutbox[1]
    html = cumple_reglas_de_correo(aviso)
    assert "No encontramos una cuenta con este correo" in html
    assert "/pages/signup.html" in html
    assert "#uid=" not in aviso.body and "token" not in aviso.body


def test_cuenta_desactivada_no_recibe_enlace_de_restablecer(api, crear_usuario, mailoutbox):
    crear_usuario(nombre="inactivo", is_active=False)
    api.post(SOLICITAR, {"correo": "inactivo@correo.com"}, format="json")
    assert len(mailoutbox) == 1
    assert "#uid=" not in mailoutbox[0].body


def test_varias_solicitudes_seguidas_envian_un_correo_cada_una(api, estudiante, mailoutbox):
    for _ in range(3):
        api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json")
    assert len(mailoutbox) == 3


@override_settings(RECUPERAR_MAX_POR_CORREO=3)
def test_hay_un_maximo_de_correos_por_hora_a_la_misma_direccion(api, estudiante, mailoutbox):
    for _ in range(5):
        assert api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json").status_code == 200
    assert len(mailoutbox) == 3


def test_cambiar_la_contrasena_desde_el_perfil_avisa_y_cierra_sesiones(api, con_jwt, estudiante, mailoutbox,
                                                                       django_capture_on_commit_callbacks):
    cliente = con_jwt(estudiante)
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = cliente.post("/api/auth/cambiar-password/",
                                 {"password_actual": CLAVE, "password_nueva": NUEVA}, format="json")
    assert respuesta.status_code == 200
    assert mailoutbox[-1].subject == "Tu contraseña de enSEÑArte cambió"
    assert "usando un enlace de recuperación" not in mailoutbox[-1].body
    assert api.post("/api/auth/refresh/", {"refresh": cliente.tokens["refresh"]}, format="json").status_code == 401
    assert OutstandingToken.objects.filter(user=estudiante, blacklistedtoken__isnull=True).count() == 0


def test_en_produccion_el_correo_sale_en_otro_hilo(api, estudiante, settings, monkeypatch):
    """La respuesta no espera al SMTP: tarda lo mismo exista o no la cuenta."""
    import threading

    lanzados = []

    class HiloFalso:
        def __init__(self, target, daemon):
            lanzados.append((target, daemon))

        def start(self):
            pass

    monkeypatch.setattr(threading, "Thread", HiloFalso)
    settings.CORREOS_EN_SEGUNDO_PLANO = True
    api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json")
    assert len(lanzados) == 1 and lanzados[0][1] is True



# ------------------------------------------------------------------ Limite general de la API


def test_limite_general_para_anonimos(api, curso, monkeypatch):
    monkeypatch.setattr(AnonRateThrottle, "THROTTLE_RATES", {**AnonRateThrottle.THROTTLE_RATES, "anon": "3/min"})
    for _ in range(3):
        assert api.get("/api/cursos/").status_code == 200
    respuesta = api.get("/api/cursos/")
    assert respuesta.status_code == 429
    assert "Retry-After" in respuesta


def test_limite_general_por_usuario(como, estudiante, curso, monkeypatch):
    monkeypatch.setattr(UserRateThrottle, "THROTTLE_RATES", {**UserRateThrottle.THROTTLE_RATES, "user": "3/min"})
    cliente = como(estudiante)
    for _ in range(3):
        assert cliente.get("/api/progreso/").status_code == 200
    assert cliente.get("/api/progreso/").status_code == 429



def test_el_correo_tiene_la_estructura_estandar(api, estudiante, mailoutbox):
    """alternative(text/plain, related(text/html, logo)): asi lo muestran bien Gmail y Outlook."""
    api.post(SOLICITAR, {"correo": "estudiante@correo.com"}, format="json")
    mensaje = mailoutbox[0].message()
    assert mensaje.get_content_type() == "multipart/alternative"
    texto, relacionada = mensaje.get_payload()
    assert texto.get_content_type() == "text/plain"
    assert relacionada.get_content_type() == "multipart/related"
    assert [p.get_content_type() for p in relacionada.get_payload()] == ["text/html", "image/png"]


def test_aviso_al_arrancar_si_el_correo_no_sale(settings):
    from apps.correos.checks import correo_configurado

    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    assert [a.id for a in correo_configurado(None)] == ["correos.W001"]
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD = "", ""
    assert [a.id for a in correo_configurado(None)] == ["correos.W002"]
    settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD = "cuenta@gmail.com", "x"
    assert correo_configurado(None) == []
