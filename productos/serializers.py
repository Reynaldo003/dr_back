#productos/serializers.py
from django.db import transaction
from django.db.models import IntegerField, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import serializers

from .models import ImagenProducto, Producto, VarianteProducto


class ImagenProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImagenProducto
        fields = ["id", "imagen", "orden"]


class VarianteProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VarianteProducto
        fields = ["id", "color", "talla", "stock"]


class ProductoListaSerializer(serializers.ModelSerializer):
    stock_total = serializers.IntegerField(read_only=True)
    stock_disponible = serializers.IntegerField(read_only=True)
    en_rebaja = serializers.BooleanField(read_only=True)
    precio_final = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    porcentaje_descuento = serializers.IntegerField(read_only=True)
    total_colores = serializers.IntegerField(read_only=True)
    total_tallas = serializers.IntegerField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            "id",
            "codigo",
            "titulo",
            "sku",
            "descripcion",
            "precio",
            "costo",
            "precio_rebaja",
            "precio_final",
            "porcentaje_descuento",
            "en_rebaja",
            "categoria",
            "estado",
            "imagen_principal",
            "stock_total",
            "stock_disponible",
            "stock_vendido",
            "es_new_arrival",
            "permite_compra",
            "fecha_creacion",
            "fecha_actualizacion",
            "total_colores",
            "total_tallas",
        ]


class ProductoSerializer(serializers.ModelSerializer):
    imagenes = ImagenProductoSerializer(many=True, required=False)
    variantes = VarianteProductoSerializer(many=True, required=False)
    stock_total = serializers.IntegerField(read_only=True)
    stock_disponible = serializers.IntegerField(read_only=True)
    en_rebaja = serializers.BooleanField(read_only=True)
    precio_final = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    porcentaje_descuento = serializers.IntegerField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            "id",
            "codigo",
            "titulo",
            "sku",
            "descripcion",
            "precio",
            "costo",
            "precio_rebaja",
            "precio_final",
            "porcentaje_descuento",
            "en_rebaja",
            "categoria",
            "estado",
            "imagen_principal",
            "imagenes",
            "variantes",
            "stock_total",
            "stock_disponible",
            "stock_vendido",
            "es_new_arrival",
            "permite_compra",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id",
            "codigo",
            "stock_total",
            "stock_disponible",
            "stock_vendido",
            "precio_final",
            "porcentaje_descuento",
            "en_rebaja",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def validate_sku(self, value):
        sku = str(value or "").strip()
        qs = Producto.objects.filter(sku__iexact=sku)

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError("Ya existe un producto con este SKU.")

        return sku

    def validate_costo(self, value):
        if value < 0:
            raise serializers.ValidationError("El costo no puede ser negativo.")
        return value

    def validate_imagenes(self, value):
        imagenes_limpias = []

        for item in value:
            imagen = str(item.get("imagen") or "").strip()
            orden = int(item.get("orden") or 0)

            if not imagen:
                continue

            imagenes_limpias.append(
                {
                    "imagen": imagen,
                    "orden": max(0, orden),
                }
            )

        return imagenes_limpias

    def validate_variantes(self, value):
        combinaciones = set()
        variantes_limpias = []

        for item in value:
            color = str(item.get("color") or "").strip()
            talla = str(item.get("talla") or "").strip()
            stock = int(item.get("stock") or 0)

            if not color:
                raise serializers.ValidationError("Cada variante debe tener color.")

            if not talla:
                raise serializers.ValidationError("Cada variante debe tener talla.")

            if stock < 0:
                raise serializers.ValidationError(
                    "El stock de una variante no puede ser negativo."
                )

            llave = (color.lower(), talla.lower())
            if llave in combinaciones:
                raise serializers.ValidationError(
                    "No puedes repetir la misma combinación de color y talla."
                )

            combinaciones.add(llave)
            variantes_limpias.append(
                {
                    "color": color,
                    "talla": talla,
                    "stock": stock,
                }
            )

        return variantes_limpias

    def validate(self, attrs):
        precio = attrs.get("precio", getattr(self.instance, "precio", None))
        precio_rebaja = attrs.get(
            "precio_rebaja",
            getattr(self.instance, "precio_rebaja", None),
        )
        es_new_arrival = attrs.get(
            "es_new_arrival",
            getattr(self.instance, "es_new_arrival", False),
        )

        if precio_rebaja is not None and precio is not None and precio_rebaja >= precio:
            raise serializers.ValidationError(
                {"precio_rebaja": "El precio de rebaja debe ser menor al precio normal."}
            )

        if es_new_arrival:
            attrs["permite_compra"] = False
            attrs["precio_rebaja"] = None

        return attrs

    def _crear_imagenes(self, producto, imagenes_data):
        if not imagenes_data:
            return

        ImagenProducto.objects.bulk_create(
            [
                ImagenProducto(
                    producto=producto,
                    imagen=item["imagen"],
                    orden=int(item.get("orden") or 0),
                )
                for item in imagenes_data
            ],
            batch_size=200,
        )

    def _crear_variantes(self, producto, variantes_data):
        if not variantes_data:
            return

        VarianteProducto.objects.bulk_create(
            [
                VarianteProducto(
                    producto=producto,
                    color=item["color"],
                    talla=item["talla"],
                    stock=int(item.get("stock") or 0),
                )
                for item in variantes_data
            ],
            batch_size=200,
        )

    def _recargar_producto(self, producto_id):
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
            .get(pk=producto_id)
        )

    @transaction.atomic
    def create(self, validated_data):
        imagenes_data = validated_data.pop("imagenes", [])
        variantes_data = validated_data.pop("variantes", [])

        producto = Producto.objects.create(**validated_data)

        self._crear_imagenes(producto, imagenes_data)
        self._crear_variantes(producto, variantes_data)

        producto.sincronizar_disponibilidad()
        return self._recargar_producto(producto.id)

    @transaction.atomic
    def update(self, instance, validated_data):
        imagenes_data = validated_data.pop("imagenes", None)
        variantes_data = validated_data.pop("variantes", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if imagenes_data is not None:
            instance.imagenes.all().delete()
            self._crear_imagenes(instance, imagenes_data)

        if variantes_data is not None:
            instance.variantes.all().delete()
            self._crear_variantes(instance, variantes_data)

        instance.sincronizar_disponibilidad()
        return self._recargar_producto(instance.id)


class ProductoPublicoListaSerializer(serializers.ModelSerializer):
    stock_total = serializers.IntegerField(read_only=True)
    stock_disponible = serializers.IntegerField(read_only=True)

    precio = serializers.DecimalField(
        source="precio_final",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    precio_original = serializers.DecimalField(
        source="precio",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    en_rebaja = serializers.BooleanField(read_only=True)
    porcentaje_descuento = serializers.IntegerField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            "id",
            "codigo",
            "titulo",
            "descripcion",
            "precio",
            "precio_original",
            "en_rebaja",
            "porcentaje_descuento",
            "categoria",
            "imagen_principal",
            "stock_total",
            "stock_disponible",
            "es_new_arrival",
            "permite_compra",
        ]


class ProductoPublicoDetalleSerializer(ProductoPublicoListaSerializer):
    imagenes = ImagenProductoSerializer(many=True, read_only=True)
    variantes = VarianteProductoSerializer(many=True, read_only=True)

    class Meta(ProductoPublicoListaSerializer.Meta):
        fields = ProductoPublicoListaSerializer.Meta.fields + [
            "imagenes",
            "variantes",
        ]