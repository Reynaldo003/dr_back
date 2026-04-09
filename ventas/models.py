import uuid
from datetime import date
from decimal import Decimal

from django.db import models

from productos.models import Producto


class Venta(models.Model):
    ESTADOS = (
        ("PENDIENTE", "Pendiente"),
        ("PAGADA", "Pagada"),
        ("CANCELADA", "Cancelada"),
        ("REEMBOLSADA", "Reembolsada"),
    )

    ESTADOS_ENVIO = (
        ("PENDIENTE", "Pendiente de envío"),
        ("EN_PROCESO", "En proceso de envío"),
        ("ENVIADO", "Enviado"),
    )

    METODOS_PAGO = (
        ("MERCADO_PAGO", "Mercado Pago"),
        ("EFECTIVO", "Efectivo"),
        ("TRANSFERENCIA", "Transferencia"),
        ("TARJETA", "Tarjeta"),
    )

    folio = models.CharField(max_length=30, unique=True, blank=True)

    cliente_usuario = models.ForeignKey(
        "clientes.Cliente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventas",
    )
    cliente_direccion = models.ForeignKey(
        "clientes.ClienteDireccion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventas",
    )

    cliente = models.CharField(max_length=180)
    cliente_email = models.EmailField(blank=True, default="")
    cliente_telefono = models.CharField(max_length=30, blank=True, default="")

    direccion_linea1 = models.CharField(max_length=255, blank=True, default="")
    direccion_linea2 = models.CharField(max_length=255, blank=True, default="")
    ciudad = models.CharField(max_length=120, blank=True, default="")
    estado_direccion = models.CharField(max_length=120, blank=True, default="")
    codigo_postal = models.CharField(max_length=20, blank=True, default="")
    referencias_envio = models.TextField(blank=True, default="")

    fecha_venta = models.DateField(default=date.today)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="PENDIENTE")
    estado_envio = models.CharField(max_length=20, choices=ESTADOS_ENVIO, default="PENDIENTE")
    metodo_pago = models.CharField(max_length=20, choices=METODOS_PAGO, default="MERCADO_PAGO")

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    referencia_externa = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    mp_preference_id = models.CharField(max_length=120, blank=True, default="")
    mp_payment_id = models.CharField(max_length=120, blank=True, default="")
    mp_status = models.CharField(max_length=60, blank=True, default="")
    mp_status_detail = models.CharField(max_length=120, blank=True, default="")
    mp_raw = models.JSONField(default=dict, blank=True)

    inventario_descontado = models.BooleanField(default=False)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ventas"
        ordering = ["-id"]

    def __str__(self):
        return self.folio or f"Venta {self.pk}"

    def save(self, *args, **kwargs):
        es_nueva = self.pk is None
        super().save(*args, **kwargs)

        if es_nueva and not self.folio:
            folio = f"V-{self.pk:05d}"
            Venta.objects.filter(pk=self.pk).update(folio=folio)
            self.folio = folio


class VentaDetalle(models.Model):
    venta = models.ForeignKey(
        Venta,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="detalles_venta",
    )
    color = models.CharField(max_length=80, blank=True, default="")
    talla = models.CharField(max_length=30, blank=True, default="")
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "ventas_detalles"
        ordering = ["id"]

    def __str__(self):
        return f"{self.venta.folio} - {self.producto.titulo}"