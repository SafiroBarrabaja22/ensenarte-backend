"""
Siembra datos iniciales para trabajar en local.

    python manage.py poblar_datos

Es idempotente: se puede correr varias veces sin duplicar registros.
"""

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cursos.models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta
from apps.cursos.permissions import GRUPO_CREADOR, GRUPO_INTERPRETE, GRUPO_PROFESOR

ABECEDARIO = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]

CURSOS = [
    {
        "nombre": "abecedario",
        "titulo": "Abecedario",
        "descripcion": "Curso basico del abecedario en lengua de senas colombiana.",
        "portada_curso": "portadaAbecedario.jpg",
        "imagen_diccionario": "portadaAbecedario.jpg",
        "imagen_evaluacion": "evaluacionInicio.jpg",
    },
    {
        "nombre": "saludos",
        "titulo": "Saludos y cortesia",
        "descripcion": "Expresiones basicas para presentarse y saludar.",
        "portada_curso": "cursos.jpg",
        "imagen_diccionario": "livres.jpg",
        "imagen_evaluacion": "evaluacionInicio.jpg",
    },
]

PALABRAS_SALUDOS = ["Hola", "Gracias", "Por favor", "Buenos dias", "Hasta luego"]


class Command(BaseCommand):
    help = "Crea los grupos de roles y carga cursos de ejemplo."

    @transaction.atomic
    def handle(self, *args, **options):
        for nombre_grupo in (GRUPO_CREADOR, GRUPO_PROFESOR, GRUPO_INTERPRETE):
            grupo, creado = Group.objects.get_or_create(name=nombre_grupo)
            self.stdout.write(
                self.style.SUCCESS(f"Grupo {nombre_grupo} creado.")
                if creado
                else f"Grupo {nombre_grupo} ya existia."
            )

        autor = User.objects.filter(is_superuser=True).first()

        for datos in CURSOS:
            curso, creado = Curso.objects.get_or_create(
                nombre=datos["nombre"],
                defaults={**datos, "creado_por": autor},
            )
            estado = "creado" if creado else "ya existia"
            self.stdout.write(f"Curso '{curso.titulo}' {estado}.")

            if curso.nombre == "abecedario":
                self._poblar_abecedario(curso)
            else:
                self._poblar_saludos(curso)

        self.stdout.write(self.style.SUCCESS("Datos de ejemplo listos."))

    def _poblar_abecedario(self, curso):
        for letra in ABECEDARIO:
            PalabraDiccionario.objects.get_or_create(
                curso=curso,
                titulo=letra,
                defaults={
                    "imagen_frontal": f"abecedario/{letra.lower()}.png",
                    "video_gif": f"abecedario/{letra.lower()}.gif",
                },
            )

            pregunta, creada = Pregunta.objects.get_or_create(
                curso=curso,
                texto=f"Cual es la sena para la letra {letra}?",
                defaults={"video": f"abecedario/{letra.lower()}.gif"},
            )
            if creada:
                distractores = [x for x in ABECEDARIO if x != letra][:3]
                OpcionPregunta.objects.create(
                    pregunta=pregunta, texto=letra, es_correcta=True
                )
                for distractor in distractores:
                    OpcionPregunta.objects.create(
                        pregunta=pregunta, texto=distractor, es_correcta=False
                    )

    def _poblar_saludos(self, curso):
        for palabra in PALABRAS_SALUDOS:
            slug = palabra.lower().replace(" ", "-")
            PalabraDiccionario.objects.get_or_create(
                curso=curso,
                titulo=palabra,
                defaults={
                    "imagen_frontal": f"saludos/{slug}.png",
                    "video_gif": f"saludos/{slug}.gif",
                },
            )

            pregunta, creada = Pregunta.objects.get_or_create(
                curso=curso,
                texto=f"Que expresion corresponde a esta sena?",
                defaults={"video": f"saludos/{slug}.gif"},
            )
            if creada:
                distractores = [p for p in PALABRAS_SALUDOS if p != palabra][:3]
                OpcionPregunta.objects.create(
                    pregunta=pregunta, texto=palabra, es_correcta=True
                )
                for distractor in distractores:
                    OpcionPregunta.objects.create(
                        pregunta=pregunta, texto=distractor, es_correcta=False
                    )
