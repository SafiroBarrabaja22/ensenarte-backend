from django.db import migrations


def retain_five_per_user(apps, schema_editor):
    Evaluacion = apps.get_model("evaluacion_camara", "EvaluacionCamara")
    usuarios = (
        Evaluacion.objects.values_list("usuario_id", flat=True)
        .distinct()
    )
    for usuario_id in list(usuarios):
        antiguas = list(
            Evaluacion.objects.filter(usuario_id=usuario_id)
            .order_by("-fecha", "-id")
            .values_list("id", flat=True)[5:]
        )
        if antiguas:
            Evaluacion.objects.filter(id__in=antiguas).delete()


class Migration(migrations.Migration):
    dependencies = [("evaluacion_camara", "0001_initial")]

    operations = [
        migrations.RunPython(retain_five_per_user, migrations.RunPython.noop)
    ]
