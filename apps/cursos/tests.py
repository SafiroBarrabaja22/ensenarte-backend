import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from apps.cursos.serializers import RecursoVisualSerializer


class RecursoVisualSerializerTests(SimpleTestCase):
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
