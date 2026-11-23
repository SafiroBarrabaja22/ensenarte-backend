import uuid
from pathlib import Path

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

# Regla de negocio: una pregunta tiene como maximo este numero de opciones.
# La aplican el serializer del panel y el trigger opcion_maximo_* (migracion 0012).
MAXIMO_OPCIONES_POR_PREGUNTA = 4


def ruta_recurso_visual(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"biblioteca/{uuid.uuid4().hex}{extension}"


class RecursoVisual(models.Model):
    class Categoria(models.TextChoices):
        RECURSO = "recurso", "Recurso de curso"
        AVATAR = "avatar", "Avatar"
        INSIGNIA = "insignia", "Insignia de curso"
        CURSO_100 = "curso_100", "Curso 100%"

    class EstadoValidacion(models.TextChoices):
        """Revision del Validador. Solo aplica a las senas (ver `es_sena`)."""

        PENDIENTE = "pendiente", "Pendiente de validacion"
        APROBADA = "aprobada", "Aprobada"
        RECHAZADA = "rechazada", "Rechazada"

    nombre = models.CharField(max_length=120)
    archivo = models.ImageField(upload_to=ruta_recurso_visual)
    categoria = models.CharField(
        max_length=12,
        choices=Categoria.choices,
        default=Categoria.RECURSO,
        db_index=True,
    )
    subido_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recursos_visuales",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    # Las senas nuevas o reemplazadas quedan "pendiente" (apps/cursos/validacion.py);
    # el resto de recursos no pasa por el Validador y queda "aprobada". El valor por
    # defecto aprueba lo que ya existia al crear la columna.
    estado_validacion = models.CharField(
        max_length=10,
        choices=EstadoValidacion.choices,
        default=EstadoValidacion.APROBADA,
        db_index=True,
    )

    class Meta:
        ordering = ("nombre", "id")
        verbose_name = "Recurso visual"
        verbose_name_plural = "Recursos visuales"

    def __str__(self):
        return self.nombre

    @property
    def es_sena(self):
        """Un gif de la categoria "recurso": la sena que revisa el Validador."""
        return (
            self.categoria == self.Categoria.RECURSO
            and Path(self.archivo.name or "").suffix.lower() == ".gif"
        )


class RevisionSena(models.Model):
    """Historial de una sena: cada decision del Validador y cada reenvio."""

    class Accion(models.TextChoices):
        APROBADA = "aprobada", "Aprobada"
        RECHAZADA = "rechazada", "Rechazada"
        REENVIADA = "reenviada", "Archivo reemplazado (vuelve a revision)"

    recurso = models.ForeignKey(
        RecursoVisual, on_delete=models.CASCADE, related_name="revisiones"
    )
    accion = models.CharField(max_length=10, choices=Accion.choices)
    comentario = models.TextField(blank=True, default="")
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="revisiones_sena",
        help_text="El Validador que decidio, o quien reemplazo el archivo.",
    )
    archivo = models.CharField(
        max_length=255, help_text="Archivo revisado (la sena puede reemplazarse despues)."
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fecha", "-id")
        verbose_name = "Revision de sena"
        verbose_name_plural = "Revisiones de senas"

    def __str__(self):
        return f"{self.recurso} -> {self.get_accion_display()}"


class Curso(models.Model):
    """Un curso de lengua de senas. `nombre` es el slug que usa el frontend."""

    nombre = models.SlugField(unique=True)
    titulo = models.CharField(max_length=100)
    portada_curso = models.CharField(
        max_length=255,
        help_text="Nombre del archivo dentro de assets/imagenes del frontend.",
    )
    icono_curso = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Imagen cuadrada de la cabecera del curso. Vacio = usa la portada.",
    )
    insignia = models.CharField(max_length=255, blank=True, default="")
    insignia_100 = models.ForeignKey(
        RecursoVisual,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cursos_insignia_100",
        limit_choices_to={"categoria": RecursoVisual.Categoria.CURSO_100},
    )
    descripcion = models.TextField(blank=True, null=True)
    preguntas_por_evaluacion = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Cuantas preguntas al azar salen en cada intento. Vacio = todas.",
    )

    creado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cursos_creados",
    )
    fecha_creacion = models.DateTimeField(default=timezone.now)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("-fecha_creacion",)

    def __str__(self):
        return self.titulo


class Pregunta(models.Model):
    """Pregunta de opcion multiple de la evaluacion de un curso."""

    curso = models.ForeignKey(
        Curso, on_delete=models.CASCADE, related_name="preguntas"
    )
    texto = models.CharField(max_length=200)
    video = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Nombre del gif dentro de assets/videos del frontend.",
    )

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.curso.titulo} -> {self.texto}"


class OpcionPregunta(models.Model):
    """Una de las (maximo 4) respuestas posibles de una pregunta."""

    pregunta = models.ForeignKey(
        Pregunta, on_delete=models.CASCADE, related_name="opciones"
    )
    texto = models.CharField(max_length=100)
    es_correcta = models.BooleanField(default=False)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        estado = "Correcta" if self.es_correcta else "Incorrecta"
        return f"{self.texto} ({estado})"


class PalabraDiccionario(models.Model):
    """Entrada del diccionario visual: imagen frontal + gif de la sena."""

    curso = models.ForeignKey(
        Curso, on_delete=models.CASCADE, related_name="diccionario"
    )
    titulo = models.CharField(max_length=100)
    imagen_frontal = models.CharField(max_length=200)
    video_gif = models.CharField(max_length=200)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("orden", "titulo")
        verbose_name = "Palabra del diccionario"
        verbose_name_plural = "Palabras del diccionario"

    def __str__(self):
        return f"{self.titulo} - {self.curso.nombre}"


class ProgresoUsuario(models.Model):
    """Resultado consolidado del ultimo intento terminado de un usuario."""

    usuario = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="progresos"
    )
    curso = models.ForeignKey(
        Curso, on_delete=models.CASCADE, related_name="progresos"
    )

    aciertos = models.PositiveIntegerField(default=0)
    errores = models.PositiveIntegerField(default=0)
    completado = models.BooleanField(default=False)
    insignia_100_ganada = models.BooleanField(default=False)
    fecha_ultima_actividad = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("usuario", "curso")
        verbose_name = "Progreso de usuario"
        verbose_name_plural = "Progresos de usuario"

    def __str__(self):
        return f"{self.usuario.username} -> {self.curso.titulo}"


class IntentoEvaluacion(models.Model):
    """
    Estado de una evaluacion en curso.

    En el monolito esto vivia en `request.session`. Con el frontend desacoplado
    no hay sesion de Django, asi que el estado se persiste en la base de datos y
    el cliente solo consulta la pregunta actual.
    """

    usuario = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="intentos"
    )
    curso = models.ForeignKey(
        Curso, on_delete=models.CASCADE, related_name="intentos"
    )

    orden = models.JSONField(
        default=list, help_text="IDs de las preguntas en orden aleatorio."
    )
    indice_actual = models.PositiveIntegerField(default=0)
    aciertos = models.PositiveIntegerField(default=0)
    errores = models.PositiveIntegerField(default=0)
    falladas = models.JSONField(
        default=list, help_text="IDs de preguntas falladas al menos una vez."
    )
    respuestas = models.JSONField(
        default=dict,
        help_text="Opciones elegidas por pregunta, en orden: {pregunta_id: [opcion_id, ...]}.",
    )
    finalizado = models.BooleanField(default=False)

    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-fecha_inicio",)
        verbose_name = "Intento de evaluacion"
        verbose_name_plural = "Intentos de evaluacion"

    def __str__(self):
        estado = "finalizado" if self.finalizado else "en curso"
        return f"{self.usuario.username} - {self.curso.nombre} ({estado})"

    @property
    def total_preguntas(self):
        return len(self.orden)

    def pregunta_actual_id(self):
        if self.finalizado or self.indice_actual >= len(self.orden):
            return None
        return self.orden[self.indice_actual]

    def mensaje_retroalimentacion(self):
        """Misma escala de mensajes que tenia la vista `retroalimentacion`."""
        if self.errores == 0:
            return "Excelente trabajo, completaste todo sin errores."
        if self.errores <= 15:
            return "Sigue practicando, vas muy bien."
        if self.errores <= 30:
            return "La practica hace al maestro."
        return "Echale un vistazo al diccionario."


class AuditoriaCurso(models.Model):
    """
    Bitacora de altas, cambios y bajas de cursos.

    La escriben SOLO los triggers curso_auditoria_* de MySQL (migracion 0012),
    no el codigo Python: asi queda registro aunque el cambio venga del admin, de
    un script o de una consulta directa a la base.
    """

    class Operacion(models.TextChoices):
        ALTA = "alta", "Alta"
        CAMBIO = "cambio", "Cambio"
        BAJA = "baja", "Baja"

    # Sin llave foranea: el registro debe sobrevivir al borrado del curso.
    curso_id = models.BigIntegerField(db_index=True)
    operacion = models.CharField(max_length=6, choices=Operacion.choices)
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,  # el trigger escribe el id tal cual; el usuario puede borrarse luego
        related_name="auditorias_curso",
        help_text="Usuario de la aplicacion (variable @ensenarte_usuario_id o creado_por).",
    )
    usuario_bd = models.CharField(
        max_length=300, blank=True, default="",
        help_text="Usuario de MySQL que ejecuto el cambio (USER()).",
    )
    fecha = models.DateTimeField()
    valores_anteriores = models.JSONField(null=True, blank=True)
    valores_nuevos = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ("-fecha", "-id")
        verbose_name = "Auditoria de curso"
        verbose_name_plural = "Auditoria de cursos"

    def __str__(self):
        return f"{self.get_operacion_display()} del curso {self.curso_id} ({self.fecha:%Y-%m-%d %H:%M})"
