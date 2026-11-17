"""
Avisa al arrancar (runserver, check, desplegar.sh) si el correo no puede salir.
Sin correo nadie puede recuperar su contrasena: el enlace solo llega por correo.
"""

from django.conf import settings
from django.core.checks import Warning, register

CONSOLA = "django.core.mail.backends.console.EmailBackend"


@register()
def correo_configurado(app_configs, **kwargs):
    if settings.EMAIL_BACKEND == CONSOLA:
        return [Warning(
            "Los correos se imprimen en la consola y NO se envian: la recuperacion de "
            "contrasena no llegara a ningun buzon.",
            hint="Configura EMAIL_HOST, EMAIL_HOST_USER y EMAIL_HOST_PASSWORD en el .env "
                 "(Gmail: docs/DESPLIEGUE.md, seccion 1.5.1).",
            id="correos.W001",
        )]
    if "smtp" in settings.EMAIL_BACKEND and not (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD):
        return [Warning(
            "SMTP sin usuario o contrasena: los correos no saldran.",
            hint="Revisa EMAIL_HOST_USER y EMAIL_HOST_PASSWORD en el .env.",
            id="correos.W002",
        )]
    return []
