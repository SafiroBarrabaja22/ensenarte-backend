from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.cursos.models import Curso


class EvaluacionCamara(models.Model):
    """
    Una sesion de evaluacion con camara (abecedario hecho con la mano).

    El reconocimiento ocurre en el navegador; el video nunca llega al servidor.
    El cliente envia los intentos al terminar y el servidor calcula el
    resultado. `umbral_aplicado` guarda el umbral vigente en ese momento para
    que el historial no cambie si luego se ajusta la configuracion.
    """

    usuario = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="evaluaciones_camara"
    )
    curso = models.ForeignKey(
        Curso,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evaluaciones_camara",
    )
    total = models.PositiveIntegerField()
    correctas = models.PositiveIntegerField()
    porcentaje = models.PositiveIntegerField(
        help_text="correctas * 100 // total (entero, redondeado hacia abajo)."
    )
    aprobado = models.BooleanField()
    umbral_aplicado = models.PositiveIntegerField(
        help_text="Porcentaje minimo para aprobar vigente al guardar."
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fecha", "-id")
        verbose_name = "Evaluacion con camara"
        verbose_name_plural = "Evaluaciones con camara"

    def __str__(self):
        estado = "aprobada" if self.aprobado else "no aprobada"
        return f"{self.usuario.username} - {self.correctas}/{self.total} ({estado})"


class IntentoCamara(models.Model):
    """Una letra que el usuario intento hacer dentro de una sesion."""

    evaluacion = models.ForeignKey(
        EvaluacionCamara, on_delete=models.CASCADE, related_name="intentos"
    )
    orden = models.PositiveIntegerField(
        help_text="Posicion del intento dentro de la sesion (desde 0)."
    )
    letra_objetivo = models.CharField(max_length=2)
    acerto = models.BooleanField()
    tiempo_ms = models.PositiveIntegerField()
    confianza = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )

    class Meta:
        ordering = ("evaluacion", "orden")
        verbose_name = "Intento con camara"
        verbose_name_plural = "Intentos con camara"

    def __str__(self):
        marca = "ok" if self.acerto else "x"
        return f"{self.letra_objetivo} ({marca})"
