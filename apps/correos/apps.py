from django.apps import AppConfig


class CorreosConfig(AppConfig):
    """Correos transaccionales en HTML (sin modelos: solo plantillas y envio)."""

    name = "apps.correos"
    verbose_name = "Correos"
