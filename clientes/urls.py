from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminClienteViewSet,
    ClienteDireccionViewSet,
    ClienteLoginAPIView,
    ClienteLogoutAPIView,
    ClienteMeAPIView,
    ClienteMiPedidoDetalleAPIView,
    ClienteMisPedidosAPIView,
    ClienteRegistroAPIView,
    ClienteTarjetaViewSet,
)

router = DefaultRouter()
router.register(r"clientes/direcciones", ClienteDireccionViewSet, basename="clientes-direcciones")
router.register(r"clientes/tarjetas", ClienteTarjetaViewSet, basename="clientes-tarjetas")
router.register(r"admin/clientes", AdminClienteViewSet, basename="admin-clientes")

urlpatterns = router.urls + [
    path("clientes/auth/registro/", ClienteRegistroAPIView.as_view(), name="clientes-registro"),
    path("clientes/auth/login/", ClienteLoginAPIView.as_view(), name="clientes-login"),
    path("clientes/auth/logout/", ClienteLogoutAPIView.as_view(), name="clientes-logout"),
    path("clientes/me/", ClienteMeAPIView.as_view(), name="clientes-me"),
    path("clientes/mis-pedidos/", ClienteMisPedidosAPIView.as_view(), name="clientes-mis-pedidos"),
    path("clientes/mis-pedidos/<int:venta_id>/", ClienteMiPedidoDetalleAPIView.as_view(), name="clientes-mi-pedido-detalle"),
]