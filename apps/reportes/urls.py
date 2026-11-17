from django.urls import path

from . import views

urlpatterns = [
    path("constancia/<slug:slug>/", views.constancia, name="reporte_constancia"),
    path("cursos/<int:pk>/progreso/", views.progreso_curso, name="reporte_progreso_curso"),
    path("plataforma/", views.plataforma, name="reporte_plataforma"),
]
