from django.urls import path

from . import views

urlpatterns = [
    path(
        "",
        views.EvaluacionCamaraListCreateView.as_view(),
        name="evaluacion_camara",
    ),
]
