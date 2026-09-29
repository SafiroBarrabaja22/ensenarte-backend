from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views, views_panel

router = DefaultRouter()
router.register("cursos", views_panel.CursoViewSet, basename="panel-cursos")
router.register("preguntas", views_panel.PreguntaViewSet, basename="panel-preguntas")
router.register("opciones", views_panel.OpcionViewSet, basename="panel-opciones")
router.register("diccionario", views_panel.PalabraViewSet, basename="panel-diccionario")
router.register("recursos", views_panel.RecursoVisualViewSet, basename="panel-recursos")

urlpatterns = [
    # --- Catalogo y contenido ---
    path("cursos/", views.lista_cursos, name="lista_cursos"),
    path("cursos/<slug:slug>/", views.detalle_curso, name="detalle_curso"),
    path(
        "cursos/<slug:slug>/diccionario/",
        views.diccionario_curso,
        name="diccionario_curso",
    ),
    path("progreso/", views.mi_progreso, name="mi_progreso"),

    # --- Evaluacion ---
    path(
        "cursos/<slug:slug>/evaluacion/iniciar/",
        views.iniciar_evaluacion,
        name="iniciar_evaluacion",
    ),
    path(
        "cursos/<slug:slug>/evaluacion/actual/",
        views.evaluacion_actual,
        name="evaluacion_actual",
    ),
    path(
        "cursos/<slug:slug>/evaluacion/responder/",
        views.responder_evaluacion,
        name="responder_evaluacion",
    ),
    path(
        "cursos/<slug:slug>/evaluacion/resultado/",
        views.resultado_evaluacion,
        name="resultado_evaluacion",
    ),

    # --- Panel administrativo ---
    path("panel/resumen/", views_panel.resumen_panel, name="resumen_panel"),
    path(
        "panel/estudiantes/estrellas/",
        views_panel.estrellas_estudiantes,
        name="estrellas_estudiantes",
    ),
    path(
        "panel/diccionario/<int:pk>/gif/",
        views_panel.subir_gif_palabra,
        name="subir_gif_palabra",
    ),
    path(
        "panel/preguntas/<int:pk>/gif/",
        views_panel.subir_gif_pregunta,
        name="subir_gif_pregunta",
    ),
    path("panel/", include(router.urls)),
]
