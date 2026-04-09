from rest_framework import serializers
from productos.models import Producto
from .models import Comentario


class ComentarioPublicCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    stars = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(min_length=10, max_length=400)
    productId = serializers.IntegerField(required=False, allow_null=True)
    productName = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_productId(self, value):
        if value in (None, ""):
            return None

        if not Producto.objects.filter(id=value).exists():
            raise serializers.ValidationError("El producto no existe.")
        return value

    def create(self, validated_data):
        product_id = validated_data.get("productId")
        product_name = validated_data.get("productName", "").strip()

        producto = None
        if product_id:
            producto = Producto.objects.filter(id=product_id).first()

        if producto and not product_name:
            product_name = getattr(producto, "titulo", "") or ""

        comentario = Comentario.objects.create(
            producto=producto,
            producto_nombre=product_name,
            nombre=validated_data["name"].strip(),
            estrellas=validated_data["stars"],
            comentario=validated_data["text"].strip(),
            estado=Comentario.ESTADO_PENDIENTE,
        )
        return comentario


class ComentarioListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nombre", read_only=True)
    stars = serializers.IntegerField(source="estrellas", read_only=True)
    text = serializers.CharField(source="comentario", read_only=True)
    product = serializers.SerializerMethodField()
    productId = serializers.SerializerMethodField()
    verified = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source="creado_en", read_only=True)
    reviewedAt = serializers.DateTimeField(source="revisado_en", read_only=True)

    class Meta:
        model = Comentario
        fields = [
            "id",
            "name",
            "stars",
            "text",
            "estado",
            "product",
            "productId",
            "verified",
            "createdAt",
            "reviewedAt",
        ]

    def get_product(self, obj):
        if obj.producto_nombre:
            return obj.producto_nombre
        if obj.producto:
            return getattr(obj.producto, "titulo", "Producto")
        return "Boutique"

    def get_productId(self, obj):
        return obj.producto_id

    def get_verified(self, obj):
        return False