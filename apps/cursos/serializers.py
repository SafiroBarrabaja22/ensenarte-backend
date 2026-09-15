from rest_framework import serializers

from .models import (
    Curso,
    IntentoEvaluacion,
    OpcionPregunta,
    PalabraDiccionario,
    Pregunta,
    ProgresoUsuario,
)


# ==========================================================
# LECTURA PUBLICA
# ==========================================================

class CursoSerializer(serializers.ModelSerializer):
    total_preguntas = serializers.IntegerField(
        source="preguntas.count", read_only=True
    )
    total_palabras = serializers.IntegerField(
        source="diccionario.count", read_only=True
    )

    class Meta:
        model = Curso
        fields = (
            "id",
            "nombre",
            "titulo",
            "descripcion",
            "portada_curso",
            "imagen_diccionario",
            "imagen_evaluacion",
            "activo",
            "total_preguntas",
            "total_palabras",
        )


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

    class Meta:
        model = ProgresoUsuario
        fields = (
            "curso",
            "curso_titulo",
            "aciertos",
            "errores",
            "completado",
            "fecha_ultima_actividad",
        )


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

class CursoPanelSerializer(serializers.ModelSerializer):
    creado_por = serializers.CharField(
        source="creado_por.username", read_only=True
    )

    class Meta:
        model = Curso
        fields = (
            "id",
            "nombre",
            "titulo",
            "descripcion",
            "portada_curso",
            "imagen_diccionario",
            "imagen_evaluacion",
            "activo",
            "creado_por",
            "fecha_creacion",
            "fecha_modificacion",
        )
        read_only_fields = ("creado_por", "fecha_creacion", "fecha_modificacion")


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
        fields = ("id", "curso", "titulo", "imagen_frontal", "video_gif")
