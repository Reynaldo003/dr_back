from django.urls import path

from .views import dashboard_resumen, exportar_reporte, reporte_preview

urlpatterns = [
    path("dashboard/resumen/", dashboard_resumen, name="dashboard_resumen"),
    path("reportes/preview/", reporte_preview, name="reporte_preview"),
    path("reportes/exportar/", exportar_reporte, name="exportar_reporte"),
]