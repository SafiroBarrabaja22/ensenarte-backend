from pathlib import Path

from rest_framework import serializers

FORMATOS_IMAGEN_PERMITIDOS = {
    ".png",
    ".gif",
    ".jpg",
    ".jpeg",
    ".jfif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".avif",
    ".heic",
    ".heif",
}

from .models import (
    Curso,
    IntentoEvaluacion,
    OpcionPregunta,
    PalabraDiccionario,
    Pregunta,
    ProgresoUsuario,
    RecursoVisual,
)


# ==========================================================
# LECTURA PUBLICA
# ==========================================================

class CursoSerializer(serializers.ModelSerializer):
    total_preguntas = serializers.SerializerMethodField()
    total_palabras = serializers.IntegerField(
        source="diccionario.count", read_only=True
    )
    insignia_100 = serializers.SerializerMethodField()

    class Meta:
        model = Curso
        fields = (
            "id",
            "nombre",
            "titulo",
            "descripcion",
            "portada_curso",
            "icono_curso",
            "insignia",
            "insignia_100",
            "activo",
            "total_preguntas",
            "total_palabras",
        )

    def get_total_preguntas(self, obj):
        """Preguntas que vera el estudiante en cada intento."""
        total = obj.preguntas.count()
        if obj.preguntas_por_evaluacion:
            return min(total, obj.preguntas_por_evaluacion)
        return total

    def get_insignia_100(self, obj):
        recurso = obj.insignia_100
        if not recurso or not recurso.archivo:
            return None
        return {
            "id": recurso.id,
            "nombre": recurso.nombre,
            "imagen": f"/{recurso.archivo.url.lstrip('/')}",
        }


class PalabraDiccionarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = PalabraDiccionario
        fields = ("id", "titulo", "imagen_frontal", "video_gif")


class OpcionPublicaSerializer(serializers.ModelSerializer):
    """Sin `es_correcta`: el cliente nunca debe recibir la respuesta."""

    class Meta:
        model = OpcionPregunta
        fields = ("id", "texto")


class PreguntaPublicaSerializer(serializers.ModelSerializer):
    opciones = serializers.SerializerMethodField()

    class Meta:
        model = Pregunta
        fields = ("id", "texto", "video", "opciones")

    def get_opciones(self, obj):
        import random

        opciones = list(obj.opciones.all())
        random.shuffle(opciones)
        return OpcionPublicaSerializer(opciones, many=True).data


class ProgresoSerializer(serializers.ModelSerializer):
    curso = serializers.CharField(source="curso.nombre", read_only=True)
    curso_titulo = serializers.CharField(source="curso.titulo", read_only=True)
    curso_insignia = serializers.SerializerMethodField()
    curso_insignia_tipo = serializers.SerializerMethodField()
    curso_insignia_nombre = serializers.SerializerMethodField()

    class Meta:
        model = ProgresoUsuario
        fields = (
            "curso",
            "curso_titulo",
            "curso_insignia",
            "curso_insignia_tipo",
            "curso_insignia_nombre",
            "insignia_100_ganada",
            "aciertos",
            "errores",
            "completado",
            "fecha_ultima_actividad",
        )

    def get_curso_insignia(self, obj):
        recurso_100 = obj.curso.insignia_100
        if obj.insignia_100_ganada and recurso_100 and recurso_100.archivo:
            return f"/{recurso_100.archivo.url.lstrip('/')}"
        insignia = getattr(obj.curso, "insignia", "") or ""
        return f"/{insignia.lstrip('/')}" if insignia else ""

    def get_curso_insignia_tipo(self, obj):
        return "curso_100" if obj.insignia_100_ganada and obj.curso.insignia_100_id else "curso_completado"

    def get_curso_insignia_nombre(self, obj):
        if obj.insignia_100_ganada and obj.curso.insignia_100_id:
            return "Curso 100%"
        return "Curso completado"


class IntentoSerializer(serializers.ModelSerializer):
    total = serializers.IntegerField(source="total_preguntas", read_only=True)
    actual = serializers.SerializerMethodField()
    pregunta = serializers.SerializerMethodField()

    class Meta:
        model = IntentoEvaluacion
        fields = (
            "id",
            "total",
            "actual",
            "aciertos",
            "errores",
            "finalizado",
            "pregunta",
        )

    def get_actual(self, obj):
        return min(obj.indice_actual + 1, obj.total_preguntas)

    def get_pregunta(self, obj):
        pregunta_id = obj.pregunta_actual_id()
        if pregunta_id is None:
            return None
        pregunta = Pregunta.objects.filter(pk=pregunta_id).first()
        if pregunta is None:
            return None
        return PreguntaPublicaSerializer(pregunta).data


# ==========================================================
# ESCRITURA (PANEL ADMINISTRATIVO)
# ==========================================================

class RecursoVisualSerializer(serializers.ModelSerializer):
    archivo = serializers.ImageField(write_only=True, required=False)
    archivo_url = serializers.SerializerMethodField()
    extension = serializers.SerializerMethodField()

    class Meta:
        model = RecursoVisual
        fields = (
            "id",
            "nombre",
            "archivo",
            "archivo_url",
            "extension",
            "categoria",
            "fecha_creacion",
        )
        read_only_fields = ("id", "archivo_url", "extension", "fecha_creacion")

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            fields["categoria"].read_only = True
        return fields

    def validate_archivo(self, archivo):
        extension = Path(archivo.name or "").suffix.lower()
        if extension not in FORMATOS_IMAGEN_PERMITIDOS:
            raise serializers.ValidationError(
                "Formatos permitidos: PNG, GIF, JPG, JPEG, JFIF, WEBP, BMP, TIFF, AVIF, HEIC y HEIF."
            )
        if archivo.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("El archivo no puede superar 10 MB.")
        return archivo

    def validate(self, attrs):
        if self.instance is None and "archivo" not in attrs:
            raise serializers.ValidationError(
                {"archivo": "Debes seleccionar una imagen."}
            )
        return attrs

    def get_archivo_url(self, obj):
        return f"/{obj.archivo.url.lstrip('/')}"

    def get_extension(self, obj):
        return Path(obj.archivo.name).suffix.lower().lstrip(".")


class CursoPanelSerializer(serializers.ModelSerializer):
    creado_por = serializers.CharField(
        source="creado_por.username", read_only=True
    )
    insignia_100 = serializers.PrimaryKeyRelatedField(
        queryset=RecursoVisual.objects.filter(
            categoria=RecursoVisual.Categoria.CURSO_100
        ),
        allow_null=True,
        required=False,
    )
    insignia_100_nombre = serializers.SerializerMethodField()
    insignia_100_url = serializers.SerializerMethodField()

    class Meta:
        model = Curso
        fields = (
            "id",
            "nombre",
            "titulo",
            "descripcion",
            "portada_curso",
            "icono_curso",
            "insignia",
            "insignia_100",
            "insignia_100_nombre",
            "insignia_100_url",
            "preguntas_por_evaluacion",
            "activo",
            "creado_por",
            "fecha_creacion",
            "fecha_modificacion",
        )
        read_only_fields = ("creado_por", "fecha_creacion", "fecha_modificacion")

    def get_insignia_100_url(self, obj):
        recurso = obj.insignia_100
        if not recurso or not recurso.archivo:
            return ""
        return f"/{recurso.archivo.url.lstrip('/')}"

    def get_insignia_100_nombre(self, obj):
        return obj.insignia_100.nombre if obj.insignia_100_id else ""


class OpcionPanelSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpcionPregunta
        fields = ("id", "pregunta", "texto", "es_correcta")

    def validate(self, attrs):
        pregunta = attrs.get("pregunta") or getattr(self.instance, "pregunta", None)
        if pregunta is None:
            return attrs

        # Se conserva el limite de 4 opciones por pregunta del panel original.
        existentes = OpcionPregunta.objects.filter(pregunta=pregunta)
        if self.instance:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.count() >= 4:
            raise serializers.ValidationError(
                "Una pregunta admite como maximo 4 opciones."
            )
        return attrs


class PreguntaPanelSerializer(serializers.ModelSerializer):
    opciones = OpcionPanelSerializer(many=True, read_only=True)

    class Meta:
        model = Pregunta
        fields = ("id", "curso", "texto", "video", "opciones")


class PalabraPanelSerializer(serializers.ModelSerializer):
    class Meta:
        model = PalabraDiccionario
        fields = ("id", "curso", "titulo", "imagen_frontal", "video_gif", "orden")
        read_only_fields = ("orden",)
