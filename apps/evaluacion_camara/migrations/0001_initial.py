import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
	initial = True

	dependencies = [
		migrations.swappable_dependency(settings.AUTH_USER_MODEL),
	]

	operations = [
		migrations.CreateModel(
			name="EvaluacionCamara",
			fields=[
				("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
				("total", models.PositiveIntegerField()),
				("correctas", models.PositiveIntegerField()),
				("porcentaje", models.PositiveIntegerField(help_text="correctas * 100 // total (entero, redondeado hacia abajo).")),
				("aprobado", models.BooleanField()),
				("umbral_aplicado", models.PositiveIntegerField(help_text="Porcentaje minimo para aprobar vigente al guardar.")),
				("fecha", models.DateTimeField(auto_now_add=True)),
				("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evaluaciones_camara", to=settings.AUTH_USER_MODEL)),
			],
			options={
				"verbose_name": "Evaluacion con camara",
				"verbose_name_plural": "Evaluaciones con camara",
				"ordering": ("-fecha", "-id"),
			},
		),
		migrations.CreateModel(
			name="IntentoCamara",
			fields=[
				("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
				("orden", models.PositiveIntegerField(help_text="Posicion del intento dentro de la sesion (desde 0).")),
				("letra_objetivo", models.CharField(max_length=2)),
				("acerto", models.BooleanField()),
				("tiempo_ms", models.PositiveIntegerField()),
				("confianza", models.FloatField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)])),
				("evaluacion", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="intentos", to="evaluacion_camara.evaluacioncamara")),
			],
			options={
				"verbose_name": "Intento con camara",
				"verbose_name_plural": "Intentos con camara",
				"ordering": ("evaluacion", "orden"),
			},
		),
	]
