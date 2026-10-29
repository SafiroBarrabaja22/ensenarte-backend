from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from apps.cursos.models import Curso, ProgresoUsuario
from apps.cursos.media_utils import url_archivo
from apps.usuarios.models import PerfilUsuario

from .models import EvaluacionCamara, IntentoCamara


class IntentoCamaraSerializer(serializers.ModelSerializer):
    letra_objetivo = serializers.CharField(min_length=1, max_length=2)
    tiempo_ms = serializers.IntegerField(min_value=0)
    confianza = serializers.FloatField(
        min_value=0.0, max_value=1.0, required=False, allow_null=True
    )

    class Meta:
        model = IntentoCamara
        fields = ("letra_objetivo", "acerto", "tiempo_ms", "confianza")

    def validate_letra_objetivo(self, valor):
        # CharField ya recorta espacios; "ll" y "LL" son la misma letra.
        return valor.upper()


class EvaluacionCamaraSerializer(serializers.ModelSerializer):
    """
    Entrada: solo `intentos`. Todo lo demas lo calcula el servidor; si el
    cliente envia `porcentaje`, `aprobado`, etc. se ignora (solo lectura).
    """

    intentos = IntentoCamaraSerializer(many=True)
    curso = serializers.SlugRelatedField(
        slug_field="nombre",
        queryset=Curso.objects.filter(activo=True),
        required=False,
        allow_null=True,
    )
    insignia_100_ganada = serializers.SerializerMethodField()
    insignia_100_nueva = serializers.SerializerMethodField()
    insignia_100 = serializers.SerializerMethodField()

    class Meta:
        model = EvaluacionCamara
        fields = (
            "id",
            "fecha",
            "curso",
            "total",
            "correctas",
            "porcentaje",
            "aprobado",
            "umbral_aplicado",
            "intentos",
            "insignia_100_ganada",
            "insignia_100_nueva",
            "insignia_100",
        )
        read_only_fields = (
            "id",
            "fecha",
            "total",
            "correctas",
            "porcentaje",
            "aprobado",
            "umbral_aplicado",
        )

    def validate_intentos(self, intentos):
        if not intentos:
            raise serializers.ValidationError("Envia al menos un intento.")
        maximo = settings.EVALUACION_CAMARA_MAX_INTENTOS
        if len(intentos) > maximo:
            raise serializers.ValidationError(
                f"Una sesion admite como maximo {maximo} intentos."
            )
        return intentos

    @transaction.atomic
    def create(self, validated_data):
        intentos = validated_data.pop("intentos")
        umbral = settings.EVALUACION_CAMARA_UMBRAL_APROBACION
        total = len(intentos)
        correctas = sum(1 for i in intentos if i["acerto"])

        curso = validated_data.pop("curso", None)
        evaluacion = EvaluacionCamara.objects.create(
            usuario=validated_data["usuario"],
            curso=curso,
            total=total,
            correctas=correctas,
            porcentaje=correctas * 100 // total,
            # Comparacion en enteros: evita errores de redondeo en el borde.
            aprobado=correctas * 100 >= umbral * total,
            umbral_aplicado=umbral,
        )
        IntentoCamara.objects.bulk_create(
            IntentoCamara(evaluacion=evaluacion, orden=n, **datos)
            for n, datos in enumerate(intentos)
        )
        # Conserva solo las cinco sesiones mas recientes por usuario.
        anteriores = list(
            EvaluacionCamara.objects.filter(
                usuario=evaluacion.usuario, curso=curso
            )
            .order_by("-fecha", "-id")
            .values_list("id", flat=True)[5:]
        )
        if anteriores:
            EvaluacionCamara.objects.filter(id__in=anteriores).delete()

        progreso = None
        insignia_100_nueva = False
        if curso and (evaluacion.aprobado or evaluacion.porcentaje == 100):
            progreso, _ = ProgresoUsuario.objects.get_or_create(
                usuario=evaluacion.usuario, curso=curso
            )
            estaba_completado = progreso.completado
            estaba_ganada = progreso.insignia_100_ganada
            if evaluacion.aprobado:
                progreso.completado = True
            if evaluacion.porcentaje == 100:
                progreso.insignia_100_ganada = True
            progreso.save()
            insignia_100_nueva = (
                evaluacion.porcentaje == 100
                and not estaba_ganada
                and bool(curso.insignia_100_id)
            )
            if evaluacion.aprobado and not estaba_completado:
                perfil, _ = PerfilUsuario.objects.get_or_create(
                    user=evaluacion.usuario
                )
                perfil.estrellas = ProgresoUsuario.objects.filter(
                    usuario=evaluacion.usuario, completado=True
                ).count()
                perfil.save(update_fields=["estrellas"])
        evaluacion.insignia_100_ganada = bool(
            progreso and progreso.insignia_100_ganada
        )
        evaluacion.insignia_100_nueva = insignia_100_nueva
        return evaluacion

    def _progreso(self, obj):
        return ProgresoUsuario.objects.filter(
            usuario=obj.usuario, curso=obj.curso
        ).select_related("curso__insignia_100").first() if obj.curso_id else None

    def get_insignia_100_ganada(self, obj):
        progreso = self._progreso(obj)
        return bool(progreso and progreso.insignia_100_ganada)

    def get_insignia_100_nueva(self, obj):
        return bool(getattr(obj, "insignia_100_nueva", False))

    def get_insignia_100(self, obj):
        progreso = self._progreso(obj)
        recurso = (
            progreso.curso.insignia_100
            if progreso and progreso.insignia_100_ganada
            else None
        )
        if not recurso or not recurso.archivo:
            return None
        return {"nombre": "Curso 100%", "imagen": url_archivo(recurso.archivo)}
