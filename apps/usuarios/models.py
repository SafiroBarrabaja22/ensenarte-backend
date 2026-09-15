from django.contrib.auth.models import User
from django.db import models


class PerfilUsuario(models.Model):
    """Datos adicionales del usuario que no cubre el modelo User de Django."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="perfil"
    )
    foto_perfil = models.ImageField(
        upload_to="fotos_perfil/",
        blank=True,
        null=True,
        help_text="Foto subida por el usuario. Si esta vacia el frontend usa un avatar por defecto.",
    )
    avatar = models.CharField(
        max_length=100,
        default="imgPredeterminadaUsuario.png",
        help_text="Nombre del avatar predefinido dentro de assets/imagenes del frontend.",
    )
    estrellas = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Perfil de usuario"
        verbose_name_plural = "Perfiles de usuario"

    def __str__(self):
        return self.user.username
