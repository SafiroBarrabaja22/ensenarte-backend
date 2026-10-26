from django.contrib import admin

from .models import EvaluacionCamara, IntentoCamara


class IntentoCamaraInline(admin.TabularInline):
    model = IntentoCamara
    extra = 0
    can_delete = False
    readonly_fields = ("orden", "letra_objetivo", "acerto", "tiempo_ms", "confianza")


@admin.register(EvaluacionCamara)
class EvaluacionCamaraAdmin(admin.ModelAdmin):
    list_display = ("usuario", "correctas", "total", "porcentaje", "aprobado", "fecha")
    list_filter = ("aprobado",)
    search_fields = ("usuario__username",)
    readonly_fields = (
        "usuario", "total", "correctas", "porcentaje", "aprobado",
        "umbral_aplicado", "fecha",
    )
    inlines = [IntentoCamaraInline]
