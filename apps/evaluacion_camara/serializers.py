from django.conf import settings
from django.db import transaction
from rest_framework import serializers

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

    class Meta:
        model = EvaluacionCamara
        fields = (
            "id",
            "fecha",
            "total",
            "correctas",
            "porcentaje",
            "aprobado",
            "umbral_aplicado",
            "intentos",
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

        evaluacion = EvaluacionCamara.objects.create(
            usuario=validated_data["usuario"],
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
        return evaluacion
