"""
Envio de correos transaccionales con plantilla HTML y version en texto plano.

Reglas que exigen los clientes de correo (Gmail, Outlook, Apple Mail):
- Maquetacion con tablas; nada de flexbox ni grid.
- Estilos SOLO en linea (atributo style). Gmail elimina los <style>. Por eso
  los colores se pasan a las plantillas como contexto (COLORES) y no como
  variables CSS, que los clientes de correo tampoco entienden.
- Ancho maximo de 600px.
- El logo va incrustado como adjunto con Content-ID (cid:), no enlazado: muchos
  clientes bloquean las imagenes remotas.

Un correo nunca debe tumbar la operacion que lo dispara (registro, evaluacion):
- Se programa con transaction.on_commit(): solo sale si la operacion se guardo.
- Cualquier error de SMTP se registra en el log y se ignora.
- EMAIL_TIMEOUT limita cuanto puede esperar el servidor SMTP.
"""

import logging
import threading
from email.mime.image import MIMEImage
from functools import partial, wraps

import django
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from config.marca import COLORES as MARCA_COLORES
from config.marca import FUENTE_CORREO, RUTA_LOGO

logger = logging.getLogger(__name__)

CID_LOGO = "logo-ensenarte"

# Colores y logo compartidos con los reportes: config/marca.py.
COLORES = {**MARCA_COLORES, "fuente": FUENTE_CORREO}


class CorreoConLogo(EmailMultiAlternatives):
    """
    EmailMultiAlternatives con el logo incrustado (Content-ID) junto al HTML.

    En las dos versiones de Django el resultado tiene la estructura estandar
    que Gmail, Outlook y Apple Mail muestran bien:

        multipart/alternative
        ├── text/plain
        └── multipart/related
            ├── text/html          (src="cid:logo-ensenarte")
            └── image/png          (Content-ID: <logo-ensenarte>)

    Django 5.2 (requirements.txt) usa la API antigua de email.mime: se arma la
    parte related a mano en _create_alternatives. Django 6 usa la API moderna:
    add_related() sobre la parte HTML.
    """

    API_MODERNA = django.VERSION >= (6, 0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logo = RUTA_LOGO.read_bytes()

    def _create_alternatives(self, msg):
        """Django 5.2: el HTML y el logo van juntos en un multipart/related."""
        if self.API_MODERNA:
            return super()._create_alternatives(msg)
        from django.core.mail.message import SafeMIMEMultipart, SafeMIMEText

        alternativa = SafeMIMEMultipart(_subtype="alternative", encoding=self.encoding)
        alternativa.attach(msg)   # text/plain
        for contenido, tipo in self.alternatives:
            if tipo != "text/html":
                alternativa.attach(self._create_mime_attachment(contenido, tipo))
                continue
            relacionada = SafeMIMEMultipart(_subtype="related", encoding=self.encoding)
            relacionada.attach(SafeMIMEText(contenido, "html", self.encoding))
            imagen = MIMEImage(self.logo, _subtype="png")
            imagen.add_header("Content-ID", f"<{CID_LOGO}>")
            imagen.add_header("Content-Disposition", "inline", filename="logo.png")
            relacionada.attach(imagen)
            alternativa.attach(relacionada)
        return alternativa

    def message(self, *args, **kwargs):
        mensaje = super().message(*args, **kwargs)
        if self.API_MODERNA:
            html = next(
                parte for parte in mensaje.walk() if parte.get_content_type() == "text/html"
            )
            html.add_related(
                self.logo, maintype="image", subtype="png", cid=f"<{CID_LOGO}>",
                disposition="inline", filename="logo.png",
            )
        return mensaje


def construir(asunto, plantilla, contexto, destinatarios):
    """Renderiza correos/<plantilla>.html y .txt y arma el mensaje."""
    contexto = {
        **contexto,
        "asunto": asunto,
        "c": COLORES,
        "cid_logo": CID_LOGO,
        "url_frontend": settings.URL_FRONTEND.rstrip("/"),
    }
    texto = render_to_string(f"correos/{plantilla}.txt", contexto)
    html = render_to_string(f"correos/{plantilla}.html", contexto)
    correo = CorreoConLogo(asunto, texto, settings.DEFAULT_FROM_EMAIL, destinatarios)
    correo.attach_alternative(html, "text/html")
    return correo


def enviar(correo):
    """Envia sin propagar errores: devuelve True si salio, False si fallo."""
    try:
        correo.send(fail_silently=False)
    except Exception:  # SMTP caido, credenciales, timeout, DNS...
        logger.exception("No se pudo enviar el correo %r a %s", correo.subject, correo.to)
        return False
    logger.info("Correo %r enviado a %s", correo.subject, correo.to)
    return True


def al_confirmar(funcion, *args):
    """
    Programa el envio para cuando la transaccion actual se confirme.
    robust=True: si el callback fallara, Django lo registra y no lo propaga.
    """
    transaction.on_commit(partial(funcion, *args), robust=True)


def en_segundo_plano(funcion, *args):
    """
    Envia en otro hilo y responde de inmediato. La recuperacion de contrasena lo
    usa para que la respuesta tarde lo mismo exista o no la cuenta. Con
    CORREOS_EN_SEGUNDO_PLANO=False (pruebas) se ejecuta en el mismo hilo.
    """
    if not settings.CORREOS_EN_SEGUNDO_PLANO:
        funcion(*args)
        return

    def tarea():
        try:
            funcion(*args)
        finally:
            connection.close()   # cada hilo abre su propia conexion a la base

    threading.Thread(target=tarea, daemon=True).start()


def sin_romper(funcion):
    """
    Un correo nunca rompe la operacion que lo dispara: cualquier error (datos
    incompletos, plantilla, SMTP) queda en el log y la funcion devuelve False.
    """
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        try:
            return funcion(*args, **kwargs)
        except Exception:
            logger.exception("Fallo al preparar el correo %s", funcion.__name__)
            return False
    return envoltura


# ---------------------------------------------------------------- Correos


@sin_romper
def enviar_bienvenida(usuario):
    """1. Bienvenida al registrarse."""
    if not usuario.email:
        return False
    correo = construir(
        "Bienvenid@ a enSEÑArte",
        "bienvenida",
        {"nombre": usuario.username},
        [usuario.email],
    )
    return enviar(correo)


@sin_romper
def enviar_resultados(usuario, curso, resultado):
    """2. Resultados al terminar una evaluacion por preguntas."""
    if not usuario.email:
        return False
    correo = construir(
        f"Tus resultados en {curso.titulo}",
        "resultados",
        {
            "nombre": usuario.username,
            "curso": curso,
            "aciertos": resultado["aciertos"],
            "errores": resultado["errores"],
            "total": resultado["total"],
            "porcentaje": resultado["porcentaje"],
            "mensaje": resultado["mensaje"],
            "insignia_100": bool(resultado.get("insignia_100_nueva")),
        },
        [usuario.email],
    )
    return enviar(correo)


@sin_romper
def avisar_curso_completado(curso, estudiante):
    """3. Aviso al profesor (creador del curso) cuando un estudiante lo completa."""
    profesor = curso.creado_por if curso is not None else None
    if profesor is None or not profesor.email or profesor.pk == estudiante.pk:
        return False
    correo = construir(
        f"{estudiante.username} completó {curso.titulo}",
        "curso_completado",
        {"profesor": profesor.username, "estudiante": estudiante.username, "curso": curso},
        [profesor.email],
    )
    return enviar(correo)


@sin_romper
def enviar_recuperacion(usuario, uid, token):
    """
    4. Enlace para restablecer la contrasena. El uid y el token van en el
    fragmento (#) de la URL: el navegador nunca lo envia a ningun servidor ni
    aparece en registros de acceso ni en la cabecera Referer.
    """
    if not usuario.email:
        return False
    correo = construir(
        "Restablece tu contraseña de enSEÑArte",
        "recuperar_password",
        {
            "nombre": usuario.username,
            "enlace": f"{settings.URL_FRONTEND.rstrip('/')}/pages/recuperar.html#uid={uid}&token={token}",
            "minutos": max(1, settings.PASSWORD_RESET_TIMEOUT // 60),
            "fecha": timezone.localtime(),
        },
        [usuario.email],
    )
    return enviar(correo)


@sin_romper
def avisar_password_cambiado(usuario, motivo="cambio"):
    """5. Aviso de que la contrasena cambio (por recuperacion o desde el perfil)."""
    if not usuario.email:
        return False
    correo = construir(
        "Tu contraseña de enSEÑArte cambió",
        "password_cambiado",
        {"nombre": usuario.username, "motivo": motivo, "fecha": timezone.localtime()},
        [usuario.email],
    )
    return enviar(correo)


@sin_romper
def avisar_recuperacion_sin_cuenta(direccion):
    """
    6. Alguien pidio recuperar la contrasena de un correo sin cuenta activa.
    Asi el correo SIEMPRE llega (quien lo pidio sabe que no hay cuenta) y la
    respuesta de la API sigue siendo la misma, sin revelar que cuentas existen.
    """
    correo = construir(
        "Solicitud de recuperación en enSEÑArte",
        "recuperar_sin_cuenta",
        {"direccion": direccion, "fecha": timezone.localtime()},
        [direccion],
    )
    return enviar(correo)
