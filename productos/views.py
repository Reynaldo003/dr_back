import math

from django.db.models import Count, F, IntegerField, Prefetch, Q, Sum, Value
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce, Lower, NullIf, Trim
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

    def _get_pagination_values(self):
        page = self._parse_positive_int(
            self.request.query_params.get("page"),
            default=1,
        )
        page_size = self._parse_positive_int(
            self.request.query_params.get("page_size"),
            default=self.default_page_size,
            max_value=self.max_page_size,
        )
        return page, page_size

    def _paginate_queryset(self, queryset):
        page, page_size = self._get_pagination_values()

        total = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        pages = math.ceil(total / page_size) if total > 0 else 1

        return queryset[start:end], {
            "count": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
            "has_previous": page > 1,
            "has_next": end < total,
        }


class ProductoQueryMixin:
    COLOR_NORMALIZADO = NullIf(Trim(Lower("variantes__color")), Value(""))
    TALLA_NORMALIZADA = NullIf(Trim(Lower("variantes__talla")), Value(""))

    def _annotate_stock(self, queryset):
        return queryset.annotate(
            _stock_total=Coalesce(
                Sum("variantes__stock"),
                Value(0),
                output_field=IntegerField(),
            )
        )

    def _annotate_resumen_admin(self, queryset):
        return queryset.annotate(
            _stock_total=Coalesce(
                Sum("variantes__stock"),
                Value(0),
                output_field=IntegerField(),
            ),
            _total_colores=Count(self.COLOR_NORMALIZADO, distinct=True),
            _total_tallas=Count(self.TALLA_NORMALIZADA, distinct=True),
        )

    def _prefetch_detalle(self, queryset):
        return queryset.prefetch_related(
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

    def _ordenar_por_ids(self, items, ids):
        por_id = {item.id: item for item in items}
        return [por_id[item_id] for item_id in ids if item_id in por_id]


class ProductoViewSet(PaginationMixin, ProductoQueryMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]
    default_page_size = 40
    max_page_size = 100
    paginate_without_params = True

    LIST_ONLY_FIELDS = (
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

    def get_serializer_class(self):
        if self.action == "list":
            return ProductoListaSerializer
        return ProductoSerializer

    def _base_queryset(self):
        return Producto.objects.all()

    def _aplicar_filtros(self, queryset):
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

    def _get_list_queryset(self):
        return self._aplicar_filtros(
            self._base_queryset().only(
                "id",
                "titulo",
                "sku",
                "codigo",
                "categoria",
                "estado",
            )
        )

    def _get_detail_queryset(self):
        return self._prefetch_detalle(self._base_queryset())

    def get_queryset(self):
        if self.action == "list":
            return self._get_list_queryset()
        return self._get_detail_queryset().order_by("-id")

    def _hidratar_listado(self, ids):
        if not ids:
            return []

        items = (
            Producto.objects
            .filter(id__in=ids)
            .only(*self.LIST_ONLY_FIELDS)
            .order_by()
            .annotate(
                _stock_total=Coalesce(
                    Sum("variantes__stock"),
                    Value(0),
                    output_field=IntegerField(),
                ),
                _total_colores=Count(self.COLOR_NORMALIZADO, distinct=True),
                _total_tallas=Count(self.TALLA_NORMALIZADA, distinct=True),
            )
        )

        return self._ordenar_por_ids(items, ids)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        if self._should_paginate():
            page_queryset, meta = self._paginate_queryset(queryset.only("id"))
            page_ids = list(page_queryset.values_list("id", flat=True))
            items = self._hidratar_listado(page_ids)

            serializer = self.get_serializer(items, many=True)
            return Response({**meta, "results": serializer.data})

        ids = list(queryset.values_list("id", flat=True))
        items = self._hidratar_listado(ids)
        serializer = self.get_serializer(items, many=True)
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


class ProductoPublicoViewSet(PaginationMixin, ProductoQueryMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    default_page_size = 24
    max_page_size = 48
    paginate_without_params = True

    PUBLIC_ONLY_FIELDS = (
        "id",
        "codigo",
        "titulo",
        "descripcion",
        "precio",
        "precio_rebaja",
        "categoria",
        "imagen_principal",
        "es_new_arrival",
        "permite_compra",
    )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductoPublicoDetalleSerializer
        return ProductoPublicoListaSerializer

    def _base_public_queryset(self):
        return Producto.objects.filter(estado="Activo")

    def _aplicar_filtros(self, queryset):
        buscar = self.request.query_params.get("buscar", "").strip()
        categoria = self.request.query_params.get("categoria", "").strip()

        if buscar:
            queryset = queryset.filter(
                Q(titulo__icontains=buscar)
                | Q(categoria__icontains=buscar)
                | Q(sku__icontains=buscar)
                | Q(codigo__icontains=buscar)
            )

        if categoria:
            queryset = queryset.filter(categoria__iexact=categoria)

        return queryset.order_by("-id")

    def get_queryset(self):
        queryset = self._base_public_queryset()

        if self.action == "retrieve":
            return self._prefetch_detalle(queryset).order_by("-id")

        return self._aplicar_filtros(
            queryset.only(
                "id",
                "titulo",
                "codigo",
                "categoria",
                "estado",
                "es_new_arrival",
                "permite_compra",
            )
        )

    def _hidratar_listado_publico(self, ids):
        if not ids:
            return []

        items = (
            Producto.objects
            .filter(id__in=ids)
            .only(*self.PUBLIC_ONLY_FIELDS)
            .order_by()
            .annotate(
                _stock_total=Coalesce(
                    Sum("variantes__stock"),
                    Value(0),
                    output_field=IntegerField(),
                )
            )
        )

        return self._ordenar_por_ids(items, ids)

    def _build_paginated_public_response(self, queryset):
        page_queryset, meta = self._paginate_queryset(queryset.only("id"))
        page_ids = list(page_queryset.values_list("id", flat=True))
        items = self._hidratar_listado_publico(page_ids)

        serializer = self.get_serializer(items, many=True)
        return Response({**meta, "results": serializer.data})

    @method_decorator(cache_page(60 * 5))
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()).filter(es_new_arrival=False)

        solo_disponibles = request.query_params.get(
            "solo_disponibles",
            "true",
        ).strip().lower()

        if solo_disponibles == "true":
            queryset = queryset.filter(permite_compra=True)

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
        queryset = self._base_public_queryset().filter(
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
            queryset = queryset.filter(permite_compra=True)

        return self._build_paginated_public_response(queryset)

    @method_decorator(cache_page(60 * 5))
    @action(detail=False, methods=["get"], url_path="new-arrivals")
    def new_arrivals(self, request):
        queryset = self._aplicar_filtros(
            self._base_public_queryset().filter(es_new_arrival=True)
        )
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