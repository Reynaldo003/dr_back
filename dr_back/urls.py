from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("dr_back.admin_urls")),
    path("api/", include("productos.urls")),
    path("api/", include("ventas.urls")),
    path("api/", include("reportes.urls")),
    path("api/", include("comentarios.urls")),
    path("api/", include("clientes.urls")),
]