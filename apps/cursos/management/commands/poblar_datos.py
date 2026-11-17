"""
Siembra datos iniciales para trabajar en local.

    python manage.py poblar_datos

Es idempotente: se puede correr varias veces sin duplicar registros.

Los grupos de roles NO se crean aqui: los crea la migracion
usuarios/0003_grupos_de_roles al correr `migrate`.

Tambien crea una cuenta de demostracion por rol (ver USUARIOS_DEMO y el README).
Por seguridad, con DEBUG=False solo se crean si se pasa --usuarios-demo.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cursos.models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta
from apps.usuarios.roles import (
    ROL_ADMINISTRADOR,
    ROL_CREADOR,
    ROL_ESTUDIANTE,
    ROL_INTERPRETE,
    ROL_PROFESOR,
    asignar_rol,
)

# Contrasena comun de las cuentas de demostracion. Documentada en el README.
CLAVE_DEMO = "Ensenarte2026!"

# (usuario, correo, rol). Dos profesores para mostrar que uno no puede editar
# los cursos del otro.
USUARIOS_DEMO = [
    ("admin_demo", "admin_demo@ensenarte.local", ROL_ADMINISTRADOR),
    ("creador_demo", "creador_demo@ensenarte.local", ROL_CREADOR),
    ("profesor_demo", "profesor_demo@ensenarte.local", ROL_PROFESOR),
    ("profesor2_demo", "profesor2_demo@ensenarte.local", ROL_PROFESOR),
    ("interprete_demo", "interprete_demo@ensenarte.local", ROL_INTERPRETE),
    ("estudiante_demo", "estudiante_demo@ensenarte.local", ROL_ESTUDIANTE),
]

ABECEDARIO = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]

CURSOS = [
    {
        "nombre": "abecedario",
        "titulo": "Abecedario",
        "descripcion": "Curso basico del abecedario en lengua de senas colombiana.",
        "portada_curso": "portadaAbecedario.jpg",
    },
    {
        "nombre": "saludos",
        "titulo": "Saludos y cortesia",
        "descripcion": "Expresiones basicas para presentarse y saludar.",
        "portada_curso": "cursos.jpg",
    },
]

PALABRAS_SALUDOS = ["Hola", "Gracias", "Por favor", "Buenos dias", "Hasta luego"]


class Command(BaseCommand):
    help = "Crea una cuenta de demostracion por rol y carga cursos de ejemplo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--usuarios-demo",
            action="store_true",
            help="Crea las cuentas de demostracion aunque DEBUG sea False.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.DEBUG or options["usuarios_demo"]:
            self._crear_usuarios_demo()
        else:
            self.stdout.write(
                self.style.WARNING(
                    "DEBUG=False: no se crean cuentas de demostracion "
                    "(usa --usuarios-demo si de verdad las necesitas)."
                )
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

    def _crear_usuarios_demo(self):
        """Crea o restablece las cuentas de demostracion con CLAVE_DEMO."""
        for nombre, correo, rol in USUARIOS_DEMO:
            usuario, creado = User.objects.get_or_create(
                username=nombre, defaults={"email": correo}
            )
            # Se restablece siempre para que la demo funcione aunque alguien
            # haya cambiado la contrasena.
            usuario.set_password(CLAVE_DEMO)
            if rol == ROL_ADMINISTRADOR:
                # Superusuario para poder asignar roles desde /admin/.
                usuario.is_staff = True
                usuario.is_superuser = True
            usuario.save()
            asignar_rol(usuario, rol)
            estado = "creado" if creado else "restablecido"
            self.stdout.write(self.style.SUCCESS(f"Usuario {nombre} ({rol}) {estado}."))

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
