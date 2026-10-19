from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cursos", "0004_retain_five_evaluation_attempts"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recursovisual",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("recurso", "Recurso de curso"),
                    ("avatar", "Avatar"),
                    ("insignia", "Insignia de curso"),
                    ("curso_100", "Curso 100%"),
                ],
                db_index=True,
                default="recurso",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="curso",
            name="insignia_100",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={"categoria": "curso_100"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cursos_insignia_100",
                to="cursos.recursovisual",
            ),
        ),
        migrations.AddField(
            model_name="progresousuario",
            name="insignia_100_ganada",
            field=models.BooleanField(default=False),
        ),
    ]
