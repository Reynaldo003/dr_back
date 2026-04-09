from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from ventas.models import Venta, VentaDetalle

from .models import Cliente, ClienteDireccion, ClienteTarjeta


class ClienteRegistroSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    confirmar_password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = Cliente
        fields = [
            "id",
            "nombre",
            "email",
            "telefono",
            "password",
            "confirmar_password",
        ]
        read_only_fields = ["id"]

    def validate_email(self, value):
        value = value.strip().lower()

        if Cliente.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Ya existe un cliente con ese correo.")

        return value

    def validate(self, attrs):
        password = attrs.get("password", "")
        confirmar_password = attrs.get("confirmar_password", "")

        if password != confirmar_password:
            raise serializers.ValidationError(
                {"confirmar_password": "Las contraseñas no coinciden."}
            )

        validate_password(password)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("confirmar_password", None)

        cliente = Cliente(**validated_data)
        cliente.email = cliente.email.strip().lower()
        cliente.set_password(password)
        cliente.save()
        return cliente


class ClienteLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ClienteMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = [
            "id",
            "nombre",
            "email",
            "telefono",
            "email_verificado",
            "fecha_creacion",
        ]
        read_only_fields = [
            "id",
            "email_verificado",
            "fecha_creacion",
        ]

    def validate_email(self, value):
        value = value.strip().lower()
        cliente = self.instance

        existe = Cliente.objects.filter(email__iexact=value).exclude(id=cliente.id).exists()
        if existe:
            raise serializers.ValidationError("Ese correo ya está registrado por otro cliente.")

        return value


class ClienteDireccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClienteDireccion
        fields = [
            "id",
            "alias",
            "destinatario",
            "telefono",
            "direccion_linea1",
            "direccion_linea2",
            "ciudad",
            "estado_direccion",
            "codigo_postal",
            "referencias_envio",
            "principal",
            "activa",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id",
            "fecha_creacion",
            "fecha_actualizacion",
        ]


class ClienteTarjetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClienteTarjeta
        fields = [
            "id",
            "proveedor",
            "titular",
            "marca",
            "ultimos4",
            "mes_expiracion",
            "anio_expiracion",
            "mp_customer_id",
            "mp_card_id",
            "principal",
            "activa",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def validate(self, attrs):
        ultimos4 = str(attrs.get("ultimos4") or "").strip()
        if len(ultimos4) != 4 or not ultimos4.isdigit():
            raise serializers.ValidationError(
                {"ultimos4": "Debes enviar solo los últimos 4 dígitos."}
            )

        return attrs


class ClientePedidoDetalleSerializer(serializers.ModelSerializer):
    producto_id = serializers.IntegerField(source="producto.id", read_only=True)
    producto_titulo = serializers.CharField(source="producto.titulo", read_only=True)

    class Meta:
        model = VentaDetalle
        fields = [
            "id",
            "producto_id",
            "producto_titulo",
            "color",
            "talla",
            "cantidad",
            "precio_unitario",
            "subtotal",
        ]


class ClientePedidoSerializer(serializers.ModelSerializer):
    detalles = ClientePedidoDetalleSerializer(many=True, read_only=True)

    class Meta:
        model = Venta
        fields = [
            "id",
            "folio",
            "fecha_venta",
            "estado",
            "estado_envio",
            "metodo_pago",
            "subtotal",
            "total",
            "direccion_linea1",
            "direccion_linea2",
            "ciudad",
            "estado_direccion",
            "codigo_postal",
            "referencias_envio",
            "mp_preference_id",
            "mp_payment_id",
            "mp_status",
            "mp_status_detail",
            "fecha_creacion",
            "detalles",
        ]


class AdminClienteDireccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClienteDireccion
        fields = [
            "id",
            "alias",
            "destinatario",
            "telefono",
            "direccion_linea1",
            "direccion_linea2",
            "ciudad",
            "estado_direccion",
            "codigo_postal",
            "referencias_envio",
            "principal",
            "activa",
        ]


class AdminClienteListSerializer(serializers.ModelSerializer):
    direcciones = AdminClienteDireccionSerializer(many=True, read_only=True)
    total_pedidos = serializers.SerializerMethodField()
    pedidos_pagados = serializers.SerializerMethodField()
    total_gastado = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            "id",
            "nombre",
            "email",
            "telefono",
            "activo",
            "email_verificado",
            "fecha_creacion",
            "total_pedidos",
            "pedidos_pagados",
            "total_gastado",
            "direcciones",
        ]

    def get_total_pedidos(self, obj):
        return obj.ventas.count()

    def get_pedidos_pagados(self, obj):
        return obj.ventas.filter(estado="PAGADA").count()

    def get_total_gastado(self, obj):
        total = Decimal("0.00")
        for venta in obj.ventas.filter(estado="PAGADA"):
            total += Decimal(venta.total or 0)
        return total