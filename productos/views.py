# productos/views.py
from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Producto
from .serializers import ProductoPublicoSerializer, ProductoSerializer


class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = (
            Producto.objects
            .prefetch_related("imagenes", "variantes")
            .all()
        )

        buscar = self.request.query_params.get("buscar", "").strip()
        tipo = self.request.query_params.get("tipo", "").strip().lower()

        if buscar:
            queryset = queryset.filter(
                Q(titulo__icontains=buscar) |
                Q(sku__icontains=buscar) |
                Q(codigo__icontains=buscar) |
                Q(categoria__icontains=buscar) |
                Q(descripcion__icontains=buscar)
            )

        if tipo == "rebajas":
            queryset = queryset.filter(
                es_new_arrival=False,
                precio_rebaja__isnull=False,
            )

        if tipo == "new-arrivals":
            queryset = queryset.filter(es_new_arrival=True)

        return queryset.order_by("-id")


class ProductoPublicoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductoPublicoSerializer
    permission_classes = [permissions.AllowAny]

    def _base_queryset(self):
        return (
            Producto.objects
            .prefetch_related("imagenes", "variantes")
            .filter(estado="Activo")
            .order_by("-id")
        )

    def _aplicar_filtros(self, queryset):
        buscar = self.request.query_params.get("buscar", "").strip()
        categoria = self.request.query_params.get("categoria", "").strip()

        if buscar:
            queryset = queryset.filter(
                Q(titulo__icontains=buscar) |
                Q(descripcion__icontains=buscar) |
                Q(categoria__icontains=buscar) |
                Q(sku__icontains=buscar) |
                Q(codigo__icontains=buscar)
            )

        if categoria:
            queryset = queryset.filter(categoria__iexact=categoria)

        return queryset

    def get_queryset(self):
        queryset = self._base_queryset().filter(es_new_arrival=False)
        return self._aplicar_filtros(queryset)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        solo_disponibles = request.query_params.get(
            "solo_disponibles",
            "true",
        ).strip().lower()

        if solo_disponibles == "true":
            queryset = [
                producto
                for producto in queryset
                if producto.stock_disponible > 0 and producto.permite_compra
            ]

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="rebajas")
    def rebajas(self, request):
        queryset = self._base_queryset().filter(
            es_new_arrival=False,
            precio_rebaja__isnull=False,
        )
        queryset = self._aplicar_filtros(queryset)
        queryset = [
            producto
            for producto in queryset
            if producto.en_rebaja and producto.stock_disponible > 0 and producto.permite_compra
        ]

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="new-arrivals")
    def new_arrivals(self, request):
        queryset = self._base_queryset().filter(es_new_arrival=True)
        queryset = self._aplicar_filtros(queryset)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="categorias")
    def categorias(self, request):
        categorias = (
            Producto.objects
            .filter(estado="Activo", es_new_arrival=False)
            .exclude(categoria__isnull=True)
            .exclude(categoria__exact="")
            .values_list("categoria", flat=True)
            .distinct()
            .order_by("categoria")
        )

        return Response([
            {
                "nombre": categoria,
                "slug": categoria.strip().lower().replace(" ", "-")
            }
            for categoria in categorias
        ])