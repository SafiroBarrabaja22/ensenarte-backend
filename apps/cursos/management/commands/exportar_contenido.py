"""
Exporta el contenido de la plataforma para compartirlo con el equipo.

    python manage.py exportar_contenido

Genera apps/cursos/fixtures/contenido.json con cursos, preguntas, opciones,
palabras del diccionario y recursos de la biblioteca. No incluye usuarios,
progreso ni intentos. Los archivos de la biblioteca viven en media/biblioteca
y media/contenido, que se suben al repositorio junto con este JSON.
"""

import json
from pathlib import Path

from django.core import serializers
from django.core.management.base import BaseCommand

from apps.cursos.models import (
    Curso,
    OpcionPregunta,
    PalabraDiccionario,
    Pregunta,
    RecursoVisual,
)

RUTA_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "contenido.json"

# Orden de carga: primero lo que otros modelos referencian.
MODELOS = (RecursoVisual, Curso, Pregunta, OpcionPregunta, PalabraDiccionario)

# Relaciones con usuarios: no se comparten, cada base tiene los suyos.
CAMPOS_USUARIO = ("subido_por", "creado_por")


class Command(BaseCommand):
    help = "Exporta el contenido (cursos, preguntas, diccionario y biblioteca) a un JSON."

    def handle(self, *args, **options):
        registros = []
        for modelo in MODELOS:
            datos = json.loads(
                serializers.serialize("json", modelo.objects.order_by("pk"))
            )
            for registro in datos:
                for campo in CAMPOS_USUARIO:
                    if campo in registro["fields"]:
                        registro["fields"][campo] = None
            registros.extend(datos)

        RUTA_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        RUTA_FIXTURE.write_text(
            json.dumps(registros, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        resumen = ", ".join(
            f"{modelo.objects.count()} {modelo._meta.verbose_name_plural}"
            for modelo in MODELOS
        )
        self.stdout.write(self.style.SUCCESS(f"Exportado a {RUTA_FIXTURE}: {resumen}."))
