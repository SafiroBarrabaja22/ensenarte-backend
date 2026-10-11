from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import EvaluacionCamara
from .serializers import EvaluacionCamaraSerializer


class EvaluacionCamaraListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/evaluacion-camara/ -> historial del usuario autenticado.
    POST /api/evaluacion-camara/ -> guarda una sesion y devuelve el resultado.

    Cuerpo del POST: {"intentos": [{"letra_objetivo": "A", "acerto": true,
                                    "tiempo_ms": 2300, "confianza": 0.8}, ...]}
    """

    serializer_class = EvaluacionCamaraSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return EvaluacionCamara.objects.filter(
            usuario=self.request.user
        ).prefetch_related("intentos")

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)
