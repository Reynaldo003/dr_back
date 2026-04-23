from django.db import transaction
from rest_framework import serializers

from .image_utils import preparar_imagen_galeria, preparar_imagen_principal
from .models import ImagenProducto, Producto, VarianteProducto


class ImagenProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImagenProducto
        fields = ["id", "imagen", "imagen_thumb", "orden"]


class VarianteProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VarianteProducto
        fields = ["id", "color", "talla", "stock"]


class ProductoListaSerializer(serializers.ModelSerializer):
    stock_total = serializers.SerializerMethodField()
    precio_rebaja = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        read_only=True,
    )
    total_colores = serializers.SerializerMethodField()
    total_tallas = serializers.SerializerMethodField()
    imagen_principal = serializers.SerializerMethodField()
    variantes = serializers.SerializerMethodField()
    en_rebaja = serializers.BooleanField(read_only=True)
    porcentaje_descuento = serializers.IntegerField(read_only=True)
    es_new_arrival = serializers.BooleanField(read_only=True)
    permite_compra = serializers.BooleanField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            "id",
            "codigo",
            "titulo",
            "sku",
            "precio",
            "precio_rebaja",
            "categoria",
            "estado",
            "imagen_principal",
            "stock_total",
            "total_colores",
            "total_tallas",
            "variantes",
            "en_rebaja",
            "porcentaje_descuento",
            "es_new_arrival",
            "permite_compra",
        ]

    def get_imagen_principal(self, obj):
        return obj.imagen_principal_thumb or obj.imagen_principal

    def _obtener_variantes(self, obj):
        cache_prefetch = getattr(obj, "_prefetched_objects_cache", {})
        variantes = cache_prefetch.get("variantes")
        if variantes is not None:
            return variantes

        return list(
            obj.variantes.only(
                "id",
                "producto_id",
                "color",
                "talla",
                "stock",
            )
        )

    def get_variantes(self, obj):
        variantes = self._obtener_variantes(obj)
        return VarianteProductoSerializer(variantes, many=True).data

    def get_stock_total(self, obj):
        stock_anotado = getattr(obj, "_stock_total", None)
        if stock_anotado is not None:
            return int(stock_anotado or 0)

        return int(obj.stock_total or 0)

    def get_total_colores(self, obj):
        total_anotado = getattr(obj, "_total_colores", None)
        if total_anotado is not None:
            return int(total_anotado or 0)

        variantes = self._obtener_variantes(obj)
        return len(
            {
                str(variante.color).strip().lower()
                for variante in variantes
                if variante.color
            }
        )

    def get_total_tallas(self, obj):
        total_anotado = getattr(obj, "_total_tallas", None)
        if total_anotado is not None:
            return int(total_anotado or 0)

        variantes = self._obtener_variantes(obj)
        return len(
            {
                str(variante.talla).strip().lower()
                for variante in variantes
                if variante.talla
            }
        )


class ProductoSerializer(serializers.ModelSerializer):
    imagenes = ImagenProductoSerializer(many=True, required=False)
    variantes = VarianteProductoSerializer(many=True, required=False)
    stock_total = serializers.SerializerMethodField()
    stock_disponible = serializers.SerializerMethodField()
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
            "imagen_principal_thumb",
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
            "imagen_principal_thumb",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def get_stock_total(self, obj):
        stock_anotado = getattr(obj, "_stock_total", None)
        if stock_anotado is not None:
            return int(stock_anotado or 0)

        return int(obj.stock_total or 0)

    def get_stock_disponible(self, obj):
        stock_anotado = getattr(obj, "_stock_total", None)
        if stock_anotado is not None:
            return int(stock_anotado or 0)

        return int(obj.stock_disponible or 0)

    def validate_sku(self, value):
        sku = str(value or "").strip()
        if not sku:
            raise serializers.ValidationError("El SKU es obligatorio.")

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

    def _obtener_variantes_para_validacion(self, attrs):
        if "variantes" in attrs:
            return attrs.get("variantes") or []

        if self.instance:
            return [
                {
                    "color": item.color,
                    "talla": item.talla,
                    "stock": int(item.stock or 0),
                }
                for item in self.instance.variantes.all()
            ]

        return []

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
        permite_compra = attrs.get(
            "permite_compra",
            getattr(self.instance, "permite_compra", True),
        )
        categoria = str(
            attrs.get("categoria", getattr(self.instance, "categoria", "")) or ""
        ).strip()
        imagen_principal = str(
            attrs.get(
                "imagen_principal",
                getattr(self.instance, "imagen_principal", ""),
            )
            or ""
        ).strip()

        if precio_rebaja is not None and precio is not None and precio_rebaja >= precio:
            raise serializers.ValidationError(
                {"precio_rebaja": "El precio de rebaja debe ser menor al precio normal."}
            )

        if es_new_arrival:
            attrs["permite_compra"] = False
            attrs["precio_rebaja"] = None
            return attrs

        if bool(permite_compra):
            variantes_fuente = self._obtener_variantes_para_validacion(attrs)
            stock_total_validacion = sum(
                int(item.get("stock") or 0) for item in variantes_fuente
            )

            if not categoria:
                raise serializers.ValidationError(
                    {"categoria": "La categoría es obligatoria para publicar en catálogo."}
                )

            if not imagen_principal:
                raise serializers.ValidationError(
                    {"imagen_principal": "La imagen principal es obligatoria para publicar en catálogo."}
                )

            if not variantes_fuente:
                raise serializers.ValidationError(
                    {"variantes": "Debes capturar al menos una variante para publicar en catálogo."}
                )

            if stock_total_validacion <= 0:
                raise serializers.ValidationError(
                    {"variantes": "El stock total debe ser mayor a 0 para publicar en catálogo."}
                )

        return attrs

    def _preparar_imagen_principal(self, imagen):
        original, thumb = preparar_imagen_principal(imagen)
        return {
            "imagen_principal": original,
            "imagen_principal_thumb": thumb,
        }

    def _normalizar_imagenes(self, imagenes_data):
        imagenes = []

        for item in imagenes_data or []:
            original, thumb = preparar_imagen_galeria(item["imagen"])
            imagenes.append(
                {
                    "imagen": original,
                    "imagen_thumb": thumb,
                    "orden": int(item.get("orden") or 0),
                }
            )

        return imagenes

    def _crear_imagenes(self, producto, imagenes_data):
        if not imagenes_data:
            return

        imagenes_normalizadas = self._normalizar_imagenes(imagenes_data)

        ImagenProducto.objects.bulk_create(
            [
                ImagenProducto(
                    producto=producto,
                    imagen=item["imagen"],
                    imagen_thumb=item["imagen_thumb"],
                    orden=int(item.get("orden") or 0),
                )
                for item in imagenes_normalizadas
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
            .prefetch_related("imagenes", "variantes")
            .get(pk=producto_id)
        )

    @transaction.atomic
    def create(self, validated_data):
        imagenes_data = validated_data.pop("imagenes", [])
        variantes_data = validated_data.pop("variantes", [])

        validated_data.update(
            self._preparar_imagen_principal(validated_data.get("imagen_principal", ""))
        )

        producto = Producto.objects.create(**validated_data)

        self._crear_imagenes(producto, imagenes_data)
        self._crear_variantes(producto, variantes_data)

        producto.sincronizar_disponibilidad(forzar_activo=not producto.es_new_arrival)
        return self._recargar_producto(producto.id)

    @transaction.atomic
    def update(self, instance, validated_data):
        imagenes_data = validated_data.pop("imagenes", None)
        variantes_data = validated_data.pop("variantes", None)

        if "imagen_principal" in validated_data:
            validated_data.update(
                self._preparar_imagen_principal(validated_data.get("imagen_principal", ""))
            )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if imagenes_data is not None:
            instance.imagenes.all().delete()
            self._crear_imagenes(instance, imagenes_data)

        if variantes_data is not None:
            instance.variantes.all().delete()
            self._crear_variantes(instance, variantes_data)

        instance.sincronizar_disponibilidad(forzar_activo=not instance.es_new_arrival)
        return self._recargar_producto(instance.id)


class ProductoPublicoListaSerializer(serializers.ModelSerializer):
    stock_total = serializers.SerializerMethodField()
    stock_disponible = serializers.SerializerMethodField()
    imagen_principal = serializers.SerializerMethodField()

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

    def get_imagen_principal(self, obj):
        return obj.imagen_principal_thumb or obj.imagen_principal

    def get_stock_total(self, obj):
        stock_anotado = getattr(obj, "_stock_total", None)
        if stock_anotado is not None:
            return int(stock_anotado or 0)

        return int(obj.stock_total or 0)

    def get_stock_disponible(self, obj):
        stock_anotado = getattr(obj, "_stock_total", None)
        if stock_anotado is not None:
            return int(stock_anotado or 0)

        return int(obj.stock_disponible or 0)


class ProductoPublicoDetalleSerializer(ProductoPublicoListaSerializer):
    imagen_principal = serializers.CharField(read_only=True)
    imagen_principal_thumb = serializers.CharField(read_only=True)
    imagenes = ImagenProductoSerializer(many=True, read_only=True)
    variantes = VarianteProductoSerializer(many=True, read_only=True)

    class Meta(ProductoPublicoListaSerializer.Meta):
        fields = ProductoPublicoListaSerializer.Meta.fields + [
            "imagen_principal_thumb",
            "imagenes",
            "variantes",
        ]