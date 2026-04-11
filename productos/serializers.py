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
        sku = value.strip()
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

    def validate_variantes(self, value):
        combinaciones = set()

        for item in value:
            color = item.get("color", "").strip().lower()
            talla = item.get("talla", "").strip().lower()
            llave = (color, talla)

            if llave in combinaciones:
                raise serializers.ValidationError(
                    "No puedes repetir la misma combinación de color y talla."
                )

            combinaciones.add(llave)

        return value

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

    def create(self, validated_data):
        imagenes_data = validated_data.pop("imagenes", [])
        variantes_data = validated_data.pop("variantes", [])

        producto = Producto.objects.create(**validated_data)

        for imagen_data in imagenes_data:
            ImagenProducto.objects.create(producto=producto, **imagen_data)

        for variante_data in variantes_data:
            VarianteProducto.objects.create(producto=producto, **variante_data)

        producto.sincronizar_disponibilidad()
        return producto

    def update(self, instance, validated_data):
        imagenes_data = validated_data.pop("imagenes", None)
        variantes_data = validated_data.pop("variantes", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if imagenes_data is not None:
            instance.imagenes.all().delete()
            for imagen_data in imagenes_data:
                ImagenProducto.objects.create(producto=instance, **imagen_data)

        if variantes_data is not None:
            instance.variantes.all().delete()
            for variante_data in variantes_data:
                VarianteProducto.objects.create(producto=instance, **variante_data)

        instance.sincronizar_disponibilidad()
        return instance


class ProductoPublicoSerializer(serializers.ModelSerializer):
    imagenes = ImagenProductoSerializer(many=True, read_only=True)
    variantes = VarianteProductoSerializer(many=True, read_only=True)
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
            "sku",
            "descripcion",
            "precio",
            "precio_original",
            "precio_rebaja",
            "en_rebaja",
            "porcentaje_descuento",
            "categoria",
            "imagen_principal",
            "imagenes",
            "variantes",
            "stock_total",
            "stock_disponible",
            "es_new_arrival",
            "permite_compra",
        ]