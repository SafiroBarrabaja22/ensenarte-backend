import io
from io import StringIO

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from PIL import Image

from apps.cursos.serializers import RecursoVisualSerializer
from apps.cursos.models import Curso, IntentoEvaluacion, ProgresoUsuario, RecursoVisual
from apps.cursos.views import _cerrar_intento
from apps.evaluacion_camara.models import EvaluacionCamara


class RecursoVisualSerializerTests(SimpleTestCase):
    def test_expone_extension_guardada_aunque_cloudinary_omita_el_sufijo(self):
        recurso = RecursoVisual(
            nombre="Letra A",
            archivo="media/biblioteca/recurso-sin-sufijo",
            archivo_url="https://res.cloudinary.com/demo/image/upload/recurso-sin-sufijo",
            extension="gif",
        )

        self.assertEqual(RecursoVisualSerializer(recurso).data["extension"], "gif")

    def test_permite_imagenes_jfif(self):
        buffer = io.BytesIO()
        Image.new("RGB", (10, 10), color="blue").save(buffer, format="JPEG")

        archivo = SimpleUploadedFile(
            "foto.jfif",
            buffer.getvalue(),
            content_type="image/jpeg",
        )

        resultado = RecursoVisualSerializer().validate_archivo(archivo)

        self.assertEqual(resultado.name, "foto.jfif")


class InsigniaCurso100Tests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("estudiante")
        self.insignia = RecursoVisual.objects.create(
            nombre="Insignia dorada",
            archivo="biblioteca/curso-100.png",
            categoria=RecursoVisual.Categoria.CURSO_100,
        )
        self.curso = Curso.objects.create(
            nombre="abecedario",
            titulo="Abecedario",
            portada_curso="",
            imagen_diccionario="",
            imagen_evaluacion="",
            insignia_100=self.insignia,
        )

    def test_insignia_se_gana_una_vez_y_no_se_pierde_con_menor_puntaje(self):
        perfecto = IntentoEvaluacion.objects.create(
            usuario=self.usuario, curso=self.curso, orden=[1, 2], aciertos=2
        )
        progreso, nueva = _cerrar_intento(perfecto)
        self.assertTrue(nueva)
        self.assertTrue(progreso.insignia_100_ganada)

        menor = IntentoEvaluacion.objects.create(
            usuario=self.usuario, curso=self.curso, orden=[1, 2], aciertos=1
        )
        progreso, nueva = _cerrar_intento(menor)
        self.assertFalse(nueva)
        self.assertTrue(progreso.insignia_100_ganada)

    def test_perfil_sustituye_insignia_de_completado_por_la_de_curso_100(self):
        progreso = ProgresoUsuario.objects.create(
            usuario=self.usuario, curso=self.curso, completado=True,
            insignia_100_ganada=True,
        )
        from apps.cursos.serializers import ProgresoSerializer

        data = ProgresoSerializer(progreso).data
        self.assertEqual(data["curso_insignia_tipo"], "curso_100")
        self.assertIn("curso-100.png", data["curso_insignia"])

    def test_comando_retroactivo_es_repetible_para_preguntas_y_camara(self):
        estudiante_camara = User.objects.create_user("estudiante_camara")
        IntentoEvaluacion.objects.create(
            usuario=self.usuario,
            curso=self.curso,
            orden=[1, 2],
            aciertos=2,
            finalizado=True,
        )
        EvaluacionCamara.objects.create(
            usuario=estudiante_camara,
            curso=self.curso,
            total=10,
            correctas=10,
            porcentaje=100,
            aprobado=True,
            umbral_aplicado=70,
        )

        primera_salida = StringIO()
        call_command("otorgar_insignias_curso_100", stdout=primera_salida)
        self.assertTrue(
            ProgresoUsuario.objects.get(
                usuario=self.usuario, curso=self.curso
            ).insignia_100_ganada
        )
        self.assertTrue(
            ProgresoUsuario.objects.get(
                usuario=estudiante_camara, curso=self.curso
            ).insignia_100_ganada
        )

        segunda_salida = StringIO()
        call_command("otorgar_insignias_curso_100", stdout=segunda_salida)
        self.assertIn("otorgadas: 0", segunda_salida.getvalue())
