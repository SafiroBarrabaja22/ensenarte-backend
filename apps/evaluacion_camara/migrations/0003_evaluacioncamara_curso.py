import django.db.models.deletion
from django.db import migrations, models


def asociar_sesiones_existentes(apps, schema_editor):
    Curso = apps.get_model("cursos", "Curso")
    EvaluacionCamara = apps.get_model("evaluacion_camara", "EvaluacionCamara")
    curso = Curso.objects.filter(nombre="abecedario").first()
    if curso:
        EvaluacionCamara.objects.filter(curso__isnull=True).update(curso=curso)


class Migration(migrations.Migration):
    dependencies = [
        ("cursos", "0005_insignia_curso_100"),
        ("evaluacion_camara", "0002_retain_five_camera_sessions"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluacioncamara",
            name="curso",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="evaluaciones_camara",
                to="cursos.curso",
            ),
        ),
        migrations.RunPython(asociar_sesiones_existentes, migrations.RunPython.noop),
    ]
