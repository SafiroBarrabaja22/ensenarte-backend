from django.db import migrations, models


def numerar_por_titulo(apps, schema_editor):
    """Conserva el orden alfabetico que se veia hasta ahora."""
    PalabraDiccionario = apps.get_model("cursos", "PalabraDiccionario")
    contadores = {}
    for palabra in PalabraDiccionario.objects.order_by("curso_id", "titulo", "id"):
        contadores[palabra.curso_id] = contadores.get(palabra.curso_id, 0) + 1
        palabra.orden = contadores[palabra.curso_id]
        palabra.save(update_fields=["orden"])


class Migration(migrations.Migration):

    dependencies = [
        ("cursos", "0005_insignia_curso_100"),
    ]

    operations = [
        migrations.AddField(
            model_name="palabradiccionario",
            name="orden",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name="palabradiccionario",
            options={
                "ordering": ("orden", "titulo"),
                "verbose_name": "Palabra del diccionario",
                "verbose_name_plural": "Palabras del diccionario",
            },
        ),
        migrations.RunPython(numerar_por_titulo, migrations.RunPython.noop),
    ]
