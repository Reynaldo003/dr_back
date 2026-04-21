#dr_back/productos/urls.py
from rest_framework.routers import DefaultRouter
from .views import ProductoPublicoViewSet, ProductoViewSet

router = DefaultRouter()
router.register(r"productos", ProductoViewSet, basename="productos")
router.register(r"public/productos", ProductoPublicoViewSet, basename="public-productos")

urlpatterns = router.urls