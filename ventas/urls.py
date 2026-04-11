#ventas/urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CheckoutMercadoPagoAPIView, VentaViewSet, webhook_mercado_pago

router = DefaultRouter()
router.register(r"ventas", VentaViewSet, basename="ventas")

urlpatterns = router.urls + [
    path("public/checkout/mercado-pago/", CheckoutMercadoPagoAPIView.as_view(), name="checkout_mercado_pago"),
    path("pagos/mercado-pago/webhook/", webhook_mercado_pago, name="webhook_mercado_pago"),
]