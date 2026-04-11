from decimal import Decimal

from rest_framework import serializers

from clientes.models import Cliente, ClienteDireccion
from productos.models import Producto, VarianteProducto

from .models import Venta, VentaDetalle

ENVIO_GRATIS_DESDE = Decimal("1500.00")
ENVIO_TARIFAS = {
    "ESTANDAR": Decimal("150.00"),
    "EXPRESS": Decimal("250.00"),
    "SIGUIENTE": Decimal("399.00"),
}


def normalizar_tipo_envio(value):
    tipo = str(value or "ESTANDAR").strip().upper()
    if tipo not in ENVIO_TARIFAS:
        raise serializers.ValidationError("Tipo de envío inválido.")
    return tipo


def calcular_costo_envio(tipo_envio, subtotal):
    if Decimal(subtotal) >= ENVIO_GRATIS_DESDE:
        return Decimal("0.00")
    return ENVIO_TARIFAS[tipo_envio]


class ProductoVentaResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = ["id", "titulo", "sku", "imagen_principal"]


class VentaDetalleSerializer(serializers.ModelSerializer):
    producto_id = serializers.IntegerField(write_only=True)
    producto = ProductoVentaResumenSerializer(read_only=True)

    class Meta:
        model = VentaDetalle
        fields = [
            "id",
            "producto_id",
            "producto",
            "color",
            "talla",
            "cantidad",
            "precio_unitario",
            "subtotal",
        ]
        read_only_fields = [
            "id",
            "precio_unitario",
            "subtotal",
            "producto",
        ]


class VentaSerializer(serializers.ModelSerializer):
    detalles = VentaDetalleSerializer(many=True)
    cliente_usuario_resumen = serializers.SerializerMethodField()
    cliente_direccion_resumen = serializers.SerializerMethodField()

    class Meta:
        model = Venta
        fields = [
            "id",
            "folio",
            "cliente",
            "cliente_email",
            "cliente_telefono",
            "direccion_linea1",
            "direccion_linea2",
            "ciudad",
            "estado_direccion",
            "codigo_postal",
            "referencias_envio",
            "tipo_envio",
            "costo_envio",
            "fecha_venta",
            "estado",
            "estado_envio",
            "metodo_pago",
            "subtotal",
            "total",
            "referencia_externa",
            "mp_preference_id",
            "mp_payment_id",
            "mp_status",
            "mp_status_detail",
            "inventario_descontado",
            "detalles",
            "fecha_creacion",
            "fecha_actualizacion",
            "cliente_usuario_resumen",
            "cliente_direccion_resumen",
        ]
        read_only_fields = [
            "id",
            "folio",
            "subtotal",
            "total",
            "referencia_externa",
            "mp_preference_id",
            "mp_payment_id",
            "mp_status",
            "mp_status_detail",
            "inventario_descontado",
            "fecha_creacion",
            "fecha_actualizacion",
            "cliente_usuario_resumen",
            "cliente_direccion_resumen",
        ]

    def get_cliente_usuario_resumen(self, obj):
        if not obj.cliente_usuario:
            return None

        return {
            "id": obj.cliente_usuario.id,
            "nombre": obj.cliente_usuario.nombre,
            "email": obj.cliente_usuario.email,
            "telefono": obj.cliente_usuario.telefono,
        }

    def get_cliente_direccion_resumen(self, obj):
        if not obj.cliente_direccion:
            return None

        return {
            "id": obj.cliente_direccion.id,
            "alias": obj.cliente_direccion.alias,
            "destinatario": obj.cliente_direccion.destinatario,
            "telefono": obj.cliente_direccion.telefono,
            "direccion_linea1": obj.cliente_direccion.direccion_linea1,
            "direccion_linea2": obj.cliente_direccion.direccion_linea2,
            "ciudad": obj.cliente_direccion.ciudad,
            "estado_direccion": obj.cliente_direccion.estado_direccion,
            "codigo_postal": obj.cliente_direccion.codigo_postal,
            "referencias_envio": obj.cliente_direccion.referencias_envio,
        }

    def _obtener_stock_extra_por_edicion(self):
        stock_extra = {}
        instance = getattr(self, "instance", None)

        if not instance:
            return stock_extra

        for detalle in instance.detalles.all():
            llave = (
                detalle.producto_id,
                (detalle.color or "").strip().lower(),
                (detalle.talla or "").strip().lower(),
            )
            stock_extra[llave] = stock_extra.get(llave, 0) + detalle.cantidad

        return stock_extra

    def validate_detalles(self, value):
        if not value:
            raise serializers.ValidationError("La venta debe tener al menos un producto.")

        acumulado = {}
        producto_ids = set()

        for item in value:
            producto_id = item["producto_id"]
            color = str(item.get("color") or "").strip()
            talla = str(item.get("talla") or "").strip()
            cantidad = int(item.get("cantidad") or 0)

            if cantidad <= 0:
                raise serializers.ValidationError("Todas las cantidades deben ser mayores a cero.")

            if not color or not talla:
                raise serializers.ValidationError("Cada detalle debe incluir color y talla.")

            llave = (producto_id, color.lower(), talla.lower())
            acumulado[llave] = acumulado.get(llave, 0) + cantidad
            producto_ids.add(producto_id)

        productos = {
            p.id: p
            for p in Producto.objects.filter(id__in=producto_ids)
        }

        variantes = {
            (
                v.producto_id,
                v.color.strip().lower(),
                v.talla.strip().lower(),
            ): v
            for v in VarianteProducto.objects.filter(producto_id__in=producto_ids)
        }

        stock_extra = self._obtener_stock_extra_por_edicion()

        for llave, cantidad in acumulado.items():
            producto_id, color, talla = llave
            producto = productos.get(producto_id)

            if not producto:
                raise serializers.ValidationError(f"El producto {producto_id} no existe.")

            variante = variantes.get(llave)
            if not variante:
                raise serializers.ValidationError(
                    f"No existe la variante {producto.titulo} / {color} / {talla}."
                )

            disponible = int(variante.stock or 0) + stock_extra.get(llave, 0)

            if cantidad > disponible:
                raise serializers.ValidationError(
                    f"Stock insuficiente para {producto.titulo} / {variante.color} / {variante.talla}. Disponible: {disponible}."
                )

        return value

    def _crear_detalles_y_totales(self, venta, detalles_data):
        subtotal = Decimal("0.00")
        producto_ids = {item["producto_id"] for item in detalles_data}
        productos = {
            p.id: p
            for p in Producto.objects.filter(id__in=producto_ids)
        }

        detalles = []

        for item in detalles_data:
            producto = productos.get(item["producto_id"])
            if not producto:
                raise serializers.ValidationError(
                    f"El producto {item['producto_id']} no existe."
                )

            cantidad = int(item["cantidad"])
            precio_unitario = Decimal(str(producto.precio_final))
            subtotal_linea = precio_unitario * cantidad

            detalles.append(
                VentaDetalle(
                    venta=venta,
                    producto=producto,
                    color=str(item.get("color") or "").strip(),
                    talla=str(item.get("talla") or "").strip(),
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                    subtotal=subtotal_linea,
                )
            )

            subtotal += subtotal_linea

        if detalles:
            VentaDetalle.objects.bulk_create(detalles)

        venta.subtotal = subtotal
        venta.total = subtotal + Decimal(str(venta.costo_envio or 0))
        venta.save(update_fields=["subtotal", "total"])

        return venta

    def create(self, validated_data):
        detalles_data = validated_data.pop("detalles", [])
        venta = Venta.objects.create(**validated_data)
        return self._crear_detalles_y_totales(venta, detalles_data)

    def update(self, instance, validated_data):
        detalles_data = validated_data.pop("detalles", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if detalles_data is not None:
            instance.detalles.all().delete()
            self._crear_detalles_y_totales(instance, detalles_data)
        else:
            instance.total = Decimal(str(instance.subtotal or 0)) + Decimal(
                str(instance.costo_envio or 0)
            )
            instance.save(update_fields=["total"])

        return instance


class CheckoutDetalleSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    color = serializers.CharField(required=False, allow_blank=True, default="")
    talla = serializers.CharField(required=False, allow_blank=True, default="")
    cantidad = serializers.IntegerField(min_value=1)


class CheckoutMercadoPagoSerializer(serializers.Serializer):
    direccion_id = serializers.IntegerField(required=False)
    tipo_envio = serializers.CharField(required=False, default="ESTANDAR")

    cliente = serializers.CharField(max_length=180, required=False, allow_blank=True)
    cliente_email = serializers.EmailField(required=False, allow_blank=True)
    cliente_telefono = serializers.CharField(required=False, allow_blank=True, max_length=30)

    direccion_linea1 = serializers.CharField(required=False, allow_blank=True, max_length=255)
    direccion_linea2 = serializers.CharField(required=False, allow_blank=True, max_length=255)
    ciudad = serializers.CharField(required=False, allow_blank=True, max_length=120)
    estado_direccion = serializers.CharField(required=False, allow_blank=True, max_length=120)
    codigo_postal = serializers.CharField(required=False, allow_blank=True, max_length=20)
    referencias_envio = serializers.CharField(required=False, allow_blank=True)

    detalles = CheckoutDetalleSerializer(many=True)

    def _obtener_cliente_autenticado(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if isinstance(user, Cliente) and user.activo:
            return user

        return None

    def validate_detalles(self, value):
        if not value:
            raise serializers.ValidationError("Debes enviar al menos un producto.")

        acumulado = {}
        producto_ids = set()

        for item in value:
            producto_id = item["producto_id"]
            color = str(item.get("color") or "").strip()
            talla = str(item.get("talla") or "").strip()
            cantidad = int(item["cantidad"])

            if not color or not talla:
                raise serializers.ValidationError("Cada producto debe incluir color y talla.")

            llave = (producto_id, color.lower(), talla.lower())
            acumulado[llave] = acumulado.get(llave, 0) + cantidad
            producto_ids.add(producto_id)

        productos = {
            p.id: p
            for p in Producto.objects.filter(id__in=producto_ids)
        }

        variantes = {
            (
                v.producto_id,
                v.color.strip().lower(),
                v.talla.strip().lower(),
            ): v
            for v in VarianteProducto.objects.filter(producto_id__in=producto_ids)
        }

        for llave, cantidad in acumulado.items():
            producto_id, _, _ = llave
            producto = productos.get(producto_id)

            if not producto:
                raise serializers.ValidationError(f"El producto {producto_id} no existe.")

            if producto.estado != "Activo" or not producto.permite_compra:
                raise serializers.ValidationError(f"{producto.titulo} no está disponible.")

            variante = variantes.get(llave)
            if not variante:
                raise serializers.ValidationError(
                    f"No existe la variante solicitada para {producto.titulo}."
                )

            if cantidad > int(variante.stock or 0):
                raise serializers.ValidationError(
                    f"Stock insuficiente para {producto.titulo} / {variante.color} / {variante.talla}. Disponible: {variante.stock}."
                )

        return value

    def validate(self, attrs):
        cliente = self._obtener_cliente_autenticado()
        direccion_id = attrs.get("direccion_id")
        direccion = None

        attrs["tipo_envio"] = normalizar_tipo_envio(attrs.get("tipo_envio", "ESTANDAR"))

        if cliente:
            attrs["cliente"] = (attrs.get("cliente") or cliente.nombre or "").strip()
            attrs["cliente_email"] = (attrs.get("cliente_email") or cliente.email or "").strip()
            attrs["cliente_telefono"] = (attrs.get("cliente_telefono") or cliente.telefono or "").strip()

            if direccion_id:
                direccion = ClienteDireccion.objects.filter(
                    id=direccion_id,
                    cliente=cliente,
                    activa=True,
                ).first()

                if not direccion:
                    raise serializers.ValidationError(
                        {"direccion_id": "La dirección no existe o no te pertenece."}
                    )
            else:
                direccion = ClienteDireccion.objects.filter(
                    cliente=cliente,
                    activa=True,
                    principal=True,
                ).first()

            if direccion:
                if not attrs.get("direccion_linea1"):
                    attrs["direccion_linea1"] = direccion.direccion_linea1
                if not attrs.get("direccion_linea2"):
                    attrs["direccion_linea2"] = direccion.direccion_linea2
                if not attrs.get("ciudad"):
                    attrs["ciudad"] = direccion.ciudad
                if not attrs.get("estado_direccion"):
                    attrs["estado_direccion"] = direccion.estado_direccion
                if not attrs.get("codigo_postal"):
                    attrs["codigo_postal"] = direccion.codigo_postal
                if not attrs.get("referencias_envio"):
                    attrs["referencias_envio"] = direccion.referencias_envio

        if not str(attrs.get("cliente") or "").strip():
            raise serializers.ValidationError({"cliente": "El nombre del cliente es obligatorio."})

        if not str(attrs.get("cliente_email") or "").strip():
            raise serializers.ValidationError({"cliente_email": "El correo del cliente es obligatorio."})

        if not str(attrs.get("direccion_linea1") or "").strip():
            raise serializers.ValidationError({"direccion_linea1": "La dirección es obligatoria."})

        if not str(attrs.get("ciudad") or "").strip():
            raise serializers.ValidationError({"ciudad": "La ciudad es obligatoria."})

        if not str(attrs.get("estado_direccion") or "").strip():
            raise serializers.ValidationError({"estado_direccion": "El estado es obligatorio."})

        attrs["_cliente_obj"] = cliente
        attrs["_direccion_obj"] = direccion
        return attrs

    def create(self, validated_data):
        detalles_data = validated_data.pop("detalles", [])
        validated_data.pop("direccion_id", None)

        cliente = validated_data.pop("_cliente_obj", None)
        direccion = validated_data.pop("_direccion_obj", None)
        tipo_envio = validated_data.pop("tipo_envio", "ESTANDAR")

        producto_ids = [item["producto_id"] for item in detalles_data]
        productos = {
            p.id: p
            for p in Producto.objects.filter(id__in=producto_ids)
        }

        subtotal = Decimal("0.00")
        for item in detalles_data:
            producto = productos[item["producto_id"]]
            cantidad = int(item["cantidad"])
            precio_unitario = Decimal(str(producto.precio_final))
            subtotal += precio_unitario * cantidad

        costo_envio = calcular_costo_envio(tipo_envio, subtotal)

        venta = Venta.objects.create(
            cliente_usuario=cliente,
            cliente_direccion=direccion,
            metodo_pago="MERCADO_PAGO",
            estado="PENDIENTE",
            estado_envio="PENDIENTE",
            tipo_envio=tipo_envio,
            costo_envio=costo_envio,
            **validated_data,
        )

        detalles = []

        for item in detalles_data:
            producto = productos[item["producto_id"]]
            cantidad = int(item["cantidad"])
            precio_unitario = Decimal(str(producto.precio_final))
            subtotal_linea = precio_unitario * cantidad

            detalles.append(
                VentaDetalle(
                    venta=venta,
                    producto=producto,
                    color=item.get("color", "").strip(),
                    talla=item.get("talla", "").strip(),
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                    subtotal=subtotal_linea,
                )
            )

        if detalles:
            VentaDetalle.objects.bulk_create(detalles)

        venta.subtotal = subtotal
        venta.total = subtotal + costo_envio
        venta.save(update_fields=["subtotal", "total"])

        return venta