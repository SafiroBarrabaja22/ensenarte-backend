"""
Deja el contenido de la base local igual al exportado por el equipo.

    python manage.py migrate
    python manage.py cargar_contenido

Reemplaza cursos, preguntas, opciones, palabras y recursos de la biblioteca
por los de apps/cursos/fixtures/contenido.json. Los usuarios se conservan;
el progreso y los intentos de evaluacion se borran porque dependen de los
cursos y preguntas que se reemplazan.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cursos.models import Curso, RecursoVisual

from .exportar_contenido import RUTA_FIXTURE


class Command(BaseCommand):
    help = "Reemplaza el contenido local por el de apps/cursos/fixtures/contenido.json."

    def add_arguments(self, parser):
        parser.add_argument(
            "--si",
            action="store_true",
            help="No pedir confirmacion.",
        )

    def handle(self, *args, **options):
        if not RUTA_FIXTURE.exists():
            raise CommandError(f"No existe {RUTA_FIXTURE}.")

        if not options["si"]:
            respuesta = input(
                "Se reemplazaran los cursos, preguntas, diccionario y biblioteca "
                "de esta base (y el progreso de los estudiantes). ¿Continuar? [s/N] "
            )
            if respuesta.strip().lower() not in ("s", "si", "sí"):
                self.stdout.write("Cancelado.")
                return

        with transaction.atomic():
            # En cascada se van preguntas, opciones, palabras, progreso e intentos.
            Curso.objects.all().delete()
            # Solo los registros: los archivos de media/ vienen del repositorio.
            RecursoVisual.objects.all().delete()
            call_command("loaddata", str(RUTA_FIXTURE), verbosity=0)

        self.stdout.write(self.style.SUCCESS("Contenido cargado."))
