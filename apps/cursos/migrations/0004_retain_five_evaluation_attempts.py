from django.db import migrations


def retain_five_per_user_and_course(apps, schema_editor):
    Intento = apps.get_model("cursos", "IntentoEvaluacion")
    grupos = Intento.objects.filter(finalizado=True).values(
        "usuario_id", "curso_id"
    ).distinct()
    for grupo in list(grupos):
        antiguos = list(
            Intento.objects.filter(
                finalizado=True,
                usuario_id=grupo["usuario_id"],
                curso_id=grupo["curso_id"],
            )
            .order_by("-fecha_inicio", "-id")
            .values_list("id", flat=True)[5:]
        )
        if antiguos:
            Intento.objects.filter(id__in=antiguos).delete()


class Migration(migrations.Migration):
    dependencies = [("cursos", "0003_curso_insignia_recursovisual_categoria")]

    operations = [
        migrations.RunPython(
            retain_five_per_user_and_course, migrations.RunPython.noop
        )
    ]
