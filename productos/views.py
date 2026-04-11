from django.db.models import Count, F, IntegerField, Q, Sum, Value
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Producto
from .serializers import (
    ProductoListaSerializer,
    ProductoPublicoSerializer,
    ProductoSerializer,
)


class ProductoViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]

    def get_serializer_class(self):
        if self.action == "list":
            return ProductoListaSerializer
        return ProductoSerializer

    def _base_queryset(self):
        return Producto.objects.annotate(
            _stock_total=Coalesce(
                Sum("variantes__stock"),
                Value(0),
                output_field=IntegerField(),
            ),
            total_colores=Count("variantes__color", distinct=True),
            total_tallas=Count("variantes__talla", distinct=True),
        )

    def get_queryset(self):
        queryset = self._base_queryset()

        if self.action != "list":
            queryset = queryset.prefetch_related("imagenes", "variantes")

        buscar = self.request.query_params.get("buscar", "").strip()
        tipo = self.request.query_params.get("tipo", "").strip().lower()

        if buscar:
            queryset = queryset.filter(
                Q(titulo__icontains=buscar)
                | Q(sku__icontains=buscar)
                | Q(codigo__icontains=buscar)
                | Q(categoria__icontains=buscar)
                | Q(descripcion__icontains=buscar)
            )

        if tipo == "rebajas":
            queryset = queryset.filter(
                es_new_arrival=False,
                precio_rebaja__isnull=False,
                precio_rebaja__gt=0,
                precio_rebaja__lt=F("precio"),
            )

        if tipo == "new-arrivals":
            queryset = queryset.filter(es_new_arrival=True)

        return queryset.order_by("-id")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "No puedes eliminar este producto porque ya tiene ventas registradas. "
                        "Para conservar el historial, márcalo como Inactivo."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductoPublicoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductoPublicoSerializer
    permission_classes = [permissions.AllowAny]

    def _base_queryset(self):
        return (
            Producto.objects
            .annotate(
                _stock_total=Coalesce(
                    Sum("variantes__stock"),
                    Value(0),
                    output_field=IntegerField(),
                )
            )
            .prefetch_related("imagenes", "variantes")
            .filter(estado="Activo")
            .order_by("-id")
        )

    def _aplicar_filtros(self, queryset):
        buscar = self.request.query_params.get("buscar", "").strip()
        categoria = self.request.query_params.get("categoria", "").strip()

        if buscar:
            queryset = queryset.filter(
                Q(titulo__icontains=buscar)
                | Q(descripcion__icontains=buscar)
                | Q(categoria__icontains=buscar)
                | Q(sku__icontains=buscar)
                | Q(codigo__icontains=buscar)
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
            queryset = queryset.filter(_stock_total__gt=0, permite_compra=True)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="rebajas")
    def rebajas(self, request):
        queryset = self._base_queryset().filter(
            es_new_arrival=False,
            precio_rebaja__isnull=False,
            precio_rebaja__gt=0,
            precio_rebaja__lt=F("precio"),
            _stock_total__gt=0,
            permite_compra=True,
        )
        queryset = self._aplicar_filtros(queryset)

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
                "slug": categoria.strip().lower().replace(" ", "-"),
            }
            for categoria in categorias
        ])