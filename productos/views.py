# productos/views.py
import math

from django.db.models import (
    Count,
    F,
    IntegerField,
    Prefetch,
    Q,
    Sum,
    Value,
)
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ImagenProducto, Producto, VarianteProducto
from .serializers import (
    ProductoListaSerializer,
    ProductoPublicoDetalleSerializer,
    ProductoPublicoListaSerializer,
    ProductoSerializer,
)


class PaginationMixin:
    default_page_size = 24
    max_page_size = 60
    paginate_without_params = False

    def _parse_positive_int(self, value, default, max_value=None):
        try:
            numero = int(value)
        except (TypeError, ValueError):
            return default

        if numero < 1:
            return default

        if max_value is not None:
            return min(numero, max_value)

        return numero

    def _should_paginate(self):
        if self.paginate_without_params:
            return True

        return (
            "page" in self.request.query_params
            or "page_size" in self.request.query_params
        )

    def _build_paginated_response(self, queryset):
        page = self._parse_positive_int(
            self.request.query_params.get("page"),
            default=1,
        )
        page_size = self._parse_positive_int(
            self.request.query_params.get("page_size"),
            default=self.default_page_size,
            max_value=self.max_page_size,
        )

        total = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        pages = math.ceil(total / page_size) if total > 0 else 1

        serializer = self.get_serializer(queryset[start:end], many=True)

        return Response(
            {
                "count": total,
                "page": page,
                "page_size": page_size,
                "pages": pages,
                "has_previous": page > 1,
                "has_next": end < total,
                "results": serializer.data,
            }
        )


class ProductoViewSet(PaginationMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]
    default_page_size = 40
    max_page_size = 100
    paginate_without_params = True

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

        if self.action == "list":
            queryset = queryset.only(
                "id",
                "codigo",
                "titulo",
                "sku",
                "precio",
                "precio_rebaja",
                "categoria",
                "estado",
                "imagen_principal",
            )
        else:
            queryset = queryset.prefetch_related(
                Prefetch(
                    "imagenes",
                    queryset=ImagenProducto.objects.only(
                        "id",
                        "producto_id",
                        "imagen",
                        "orden",
                    ),
                ),
                Prefetch(
                    "variantes",
                    queryset=VarianteProducto.objects.only(
                        "id",
                        "producto_id",
                        "color",
                        "talla",
                        "stock",
                    ),
                ),
            )

        buscar = self.request.query_params.get("buscar", "").strip()
        tipo = self.request.query_params.get("tipo", "").strip().lower()
        categoria = self.request.query_params.get("categoria", "").strip()
        estado = self.request.query_params.get("estado", "").strip()

        if buscar:
            queryset = queryset.filter(
                Q(titulo__icontains=buscar)
                | Q(sku__icontains=buscar)
                | Q(codigo__icontains=buscar)
                | Q(categoria__icontains=buscar)
                | Q(descripcion__icontains=buscar)
            )

        if categoria:
            queryset = queryset.filter(categoria__iexact=categoria)

        if estado:
            queryset = queryset.filter(estado__iexact=estado)

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

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        if self._should_paginate():
            return self._build_paginated_response(queryset)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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


class ProductoPublicoViewSet(PaginationMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    default_page_size = 24
    max_page_size = 48
    paginate_without_params = True

    PUBLIC_ONLY_FIELDS = (
        "id",
        "codigo",
        "titulo",
        "sku",
        "descripcion",
        "precio",
        "precio_rebaja",
        "categoria",
        "imagen_principal",
        "es_new_arrival",
        "permite_compra",
        "estado",
    )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductoPublicoDetalleSerializer
        return ProductoPublicoListaSerializer

    def _annotate_stock_total(self, queryset):
        return queryset.annotate(
            _stock_total=Coalesce(
                Sum("variantes__stock"),
                Value(0),
                output_field=IntegerField(),
            )
        )

    def _base_public_queryset(self):
        return Producto.objects.filter(estado="Activo").only(*self.PUBLIC_ONLY_FIELDS)

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
        queryset = self._base_public_queryset()
        queryset = self._annotate_stock_total(queryset)

        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                Prefetch(
                    "imagenes",
                    queryset=ImagenProducto.objects.only(
                        "id",
                        "producto_id",
                        "imagen",
                        "orden",
                    ),
                ),
                Prefetch(
                    "variantes",
                    queryset=VarianteProducto.objects.only(
                        "id",
                        "producto_id",
                        "color",
                        "talla",
                        "stock",
                    ),
                ),
            )

        return queryset.order_by("-id")

    def _build_paginated_public_response(self, queryset):
        page = self._parse_positive_int(
            self.request.query_params.get("page"),
            default=1,
        )
        page_size = self._parse_positive_int(
            self.request.query_params.get("page_size"),
            default=self.default_page_size,
            max_value=self.max_page_size,
        )

        total = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        pages = math.ceil(total / page_size) if total > 0 else 1

        serializer = self.get_serializer(queryset[start:end], many=True)

        return Response(
            {
                "count": total,
                "page": page,
                "page_size": page_size,
                "pages": pages,
                "has_previous": page > 1,
                "has_next": end < total,
                "results": serializer.data,
            }
        )

    @method_decorator(cache_page(60 * 5))
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()).filter(es_new_arrival=False)
        queryset = self._aplicar_filtros(queryset)

        solo_disponibles = request.query_params.get(
            "solo_disponibles",
            "true",
        ).strip().lower()

        if solo_disponibles == "true":
            queryset = queryset.filter(_stock_total__gt=0, permite_compra=True)

        return self._build_paginated_public_response(queryset)

    @method_decorator(cache_page(60 * 5))
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.es_new_arrival:
            return Response({"detail": "Producto no disponible."}, status=404)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @method_decorator(cache_page(60 * 5))
    @action(detail=False, methods=["get"], url_path="rebajas")
    def rebajas(self, request):
        queryset = self.get_queryset().filter(
            es_new_arrival=False,
            precio_rebaja__isnull=False,
            precio_rebaja__gt=0,
            precio_rebaja__lt=F("precio"),
        )
        queryset = self._aplicar_filtros(queryset)

        solo_disponibles = request.query_params.get(
            "solo_disponibles",
            "true",
        ).strip().lower()

        if solo_disponibles == "true":
            queryset = queryset.filter(_stock_total__gt=0, permite_compra=True)

        return self._build_paginated_public_response(queryset)

    @method_decorator(cache_page(60 * 5))
    @action(detail=False, methods=["get"], url_path="new-arrivals")
    def new_arrivals(self, request):
        queryset = self.get_queryset().filter(es_new_arrival=True)
        queryset = self._aplicar_filtros(queryset)
        return self._build_paginated_public_response(queryset)

    @method_decorator(cache_page(60 * 10))
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

        return Response(
            [
                {
                    "nombre": categoria,
                    "slug": categoria.strip().lower().replace(" ", "-"),
                }
                for categoria in categorias
            ]
        )