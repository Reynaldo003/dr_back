from django.urls import path
from .views import (
    ComentarioAdminListView,
    ComentarioAprobarView,
    ComentarioPublicView,
    ComentarioRechazarView,
)

urlpatterns = [
    path("comentarios/", ComentarioPublicView.as_view(), name="comentarios-publicos"),
    path("comentarios/admin/", ComentarioAdminListView.as_view(), name="comentarios-admin"),
    path(
        "comentarios/admin/<int:pk>/aprobar/",
        ComentarioAprobarView.as_view(),
        name="comentario-aprobar",
    ),
    path(
        "comentarios/admin/<int:pk>/rechazar/",
        ComentarioRechazarView.as_view(),
        name="comentario-rechazar",
    ),
]