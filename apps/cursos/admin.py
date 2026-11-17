from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import BaseInlineFormSet

from .models import (
    MAXIMO_OPCIONES_POR_PREGUNTA,
    AuditoriaCurso,
    Curso,
    IntentoEvaluacion,
    OpcionPregunta,
    PalabraDiccionario,
    Pregunta,
    ProgresoUsuario,
)


class OpcionInlineFormSet(BaseInlineFormSet):
    """
    Valida las opciones de una pregunta ANTES de llegar a la base, para que el
    admin muestre un error normal en vez de un 500 por el SIGNAL de los
    triggers opcion_una_correcta_* y opcion_maximo_* (que siguen siendo la
    ultima linea de defensa).
    """

    def clean(self):
        super().clean()
        if any(self.errors):
            return  # primero que se corrijan los errores de cada fila
        vigentes = [
            formulario for formulario in self.forms
            if formulario.cleaned_data and not formulario.cleaned_data.get("DELETE", False)
        ]
        if len(vigentes) > MAXIMO_OPCIONES_POR_PREGUNTA:
            raise ValidationError(
                f"Una pregunta admite como máximo {MAXIMO_OPCIONES_POR_PREGUNTA} opciones; "
                f"hay {len(vigentes)}. Borra las que sobran.",
                code="demasiadas_opciones",
            )
        correctas = sum(1 for formulario in vigentes if formulario.cleaned_data.get("es_correcta"))
        if correctas > 1:
            raise ValidationError(
                f"Solo una opción puede ser la correcta y marcaste {correctas}.",
                code="varias_correctas",
            )


class OpcionInline(admin.TabularInline):
    model = OpcionPregunta
    formset = OpcionInlineFormSet
    extra = MAXIMO_OPCIONES_POR_PREGUNTA
    max_num = MAXIMO_OPCIONES_POR_PREGUNTA


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "nombre", "activo", "creado_por", "fecha_creacion")
    list_filter = ("activo",)
    search_fields = ("titulo", "nombre")
    prepopulated_fields = {"nombre": ("titulo",)}


@admin.register(Pregunta)
class PreguntaAdmin(admin.ModelAdmin):
    list_display = ("texto", "curso")
    list_filter = ("curso",)
    search_fields = ("texto",)
    inlines = [OpcionInline]

    def save_formset(self, request, form, formset, change):
        """
        Guarda las opciones en un orden que los triggers aceptan: primero los
        borrados, luego las opciones que no son correctas y al final la
        correcta. Si se guardaran en el orden del formulario, cambiar la
        correcta de D a A marcaria A mientras D aun lo es, y el trigger
        opcion_una_correcta_update lo rechazaria aunque el formulario sea valido.
        """
        if formset.model is not OpcionPregunta:
            return super().save_formset(request, form, formset, change)
        instancias = formset.save(commit=False)
        with transaction.atomic():
            for borrada in formset.deleted_objects:
                borrada.delete()
            for opcion in sorted(instancias, key=lambda o: o.es_correcta):   # False antes que True
                opcion.save()
            formset.save_m2m()


@admin.register(PalabraDiccionario)
class PalabraDiccionarioAdmin(admin.ModelAdmin):
    list_display = ("titulo", "curso")
    list_filter = ("curso",)
    search_fields = ("titulo",)


@admin.register(ProgresoUsuario)
class ProgresoUsuarioAdmin(admin.ModelAdmin):
    list_display = ("usuario", "curso", "aciertos", "errores", "completado")
    list_filter = ("curso", "completado")


@admin.register(IntentoEvaluacion)
class IntentoEvaluacionAdmin(admin.ModelAdmin):
    list_display = ("usuario", "curso", "indice_actual", "aciertos", "errores", "finalizado")
    list_filter = ("curso", "finalizado")


@admin.register(AuditoriaCurso)
class AuditoriaCursoAdmin(admin.ModelAdmin):
    """Solo lectura: la escriben los triggers curso_auditoria_* de MySQL."""

    list_display = ("fecha", "operacion", "curso_id", "usuario", "usuario_bd")
    list_filter = ("operacion",)
    search_fields = ("curso_id", "usuario__username")
    date_hierarchy = "fecha"
    readonly_fields = [f.name for f in AuditoriaCurso._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
