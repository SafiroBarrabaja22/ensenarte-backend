from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cursos.models import IntentoEvaluacion, ProgresoUsuario
from apps.evaluacion_camara.models import EvaluacionCamara
from apps.usuarios.models import PerfilUsuario


class Command(BaseCommand):
    help = "Otorga de forma repetible la insignia Curso 100% por resultados perfectos existentes."

    @transaction.atomic
    def handle(self, *args, **options):
        perfectos = set()
        for intento in IntentoEvaluacion.objects.filter(
            finalizado=True, curso__insignia_100__isnull=False
        ).select_related("curso"):
            total = len(intento.orden or [])
            if total and intento.aciertos == total:
                perfectos.add((intento.usuario_id, intento.curso_id))

        sesiones = EvaluacionCamara.objects.filter(
            curso__insignia_100__isnull=False, porcentaje=100
        ).values_list("usuario_id", "curso_id")
        perfectos.update(sesiones)

        otorgadas = 0
        for usuario_id, curso_id in perfectos:
            progreso, creado = ProgresoUsuario.objects.get_or_create(
                usuario_id=usuario_id,
                curso_id=curso_id,
                defaults={"completado": True, "insignia_100_ganada": True},
            )
            if not creado and not progreso.insignia_100_ganada:
                se_completo = progreso.completado
                progreso.insignia_100_ganada = True
                progreso.completado = True
                progreso.save(update_fields=["insignia_100_ganada", "completado", "fecha_ultima_actividad"])
                otorgadas += 1
                if not se_completo:
                    self._actualizar_estrellas(usuario_id)
            elif creado:
                otorgadas += 1
                self._actualizar_estrellas(usuario_id)

        self.stdout.write(
            self.style.SUCCESS(
                f"Insignias Curso 100% otorgadas: {otorgadas}. "
                f"Resultados perfectos revisados: {len(perfectos)}."
            )
        )

    @staticmethod
    def _actualizar_estrellas(usuario_id):
        perfil, _ = PerfilUsuario.objects.get_or_create(user_id=usuario_id)
        perfil.estrellas = ProgresoUsuario.objects.filter(
            usuario_id=usuario_id, completado=True
        ).count()
        perfil.save(update_fields=["estrellas"])
