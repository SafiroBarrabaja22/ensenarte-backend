from django.contrib import admin

from .models import (
    Curso,
    IntentoEvaluacion,
    OpcionPregunta,
    PalabraDiccionario,
    Pregunta,
    ProgresoUsuario,
)


class OpcionInline(admin.TabularInline):
    model = OpcionPregunta
    extra = 4
    max_num = 4


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
