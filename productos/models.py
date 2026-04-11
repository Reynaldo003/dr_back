from decimal import Decimal

from django.db import models
from django.db.models import Sum


class Producto(models.Model):
    ESTADOS = (
        ("Activo", "Activo"),
        ("Inactivo", "Inactivo"),
    )

    codigo = models.CharField(max_length=20, unique=True, blank=True)
    titulo = models.CharField(max_length=200)
    sku = models.CharField(max_length=80, unique=True)
    descripcion = models.TextField(blank=True, default="")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    costo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    precio_rebaja = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    categoria = models.CharField(max_length=100, blank=True, default="")
    estado = models.CharField(max_length=10, choices=ESTADOS, default="Activo")
    imagen_principal = models.TextField(blank=True, default="")
    stock_vendido = models.PositiveIntegerField(default=0)

    es_new_arrival = models.BooleanField(default=False)
    permite_compra = models.BooleanField(default=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "productos"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.codigo or self.pk} - {self.titulo}"

    @property
    def stock_total(self):
        total = self.variantes.aggregate(total=Sum("stock")).get("total")
        return int(total or 0)

    @property
    def stock_disponible(self):
        return self.stock_total

    @property
    def en_rebaja(self):
        return (
            self.precio_rebaja is not None
            and self.precio_rebaja > 0
            and self.precio_rebaja < self.precio
        )

    @property
    def precio_final(self):
        return self.precio_rebaja if self.en_rebaja else self.precio

    @property
    def porcentaje_descuento(self):
        if not self.en_rebaja or not self.precio:
            return 0

        descuento = ((self.precio - self.precio_rebaja) / self.precio) * 100
        return round(descuento)

    def sincronizar_disponibilidad(self, forzar_activo=False):
        if not self.pk:
            return

        total = self.stock_total
        cambios = {}

        if total <= 0:
            cambios["estado"] = "Inactivo"
            cambios["permite_compra"] = False
        else:
            if not self.es_new_arrival:
                cambios["permite_compra"] = True

            if forzar_activo:
                cambios["estado"] = "Activo"

        if cambios:
            Producto.objects.filter(pk=self.pk).update(**cambios)
            for campo, valor in cambios.items():
                setattr(self, campo, valor)

    def save(self, *args, **kwargs):
        es_nuevo = self.pk is None

        if self.es_new_arrival:
            self.permite_compra = False
            self.precio_rebaja = None

        if self.precio_rebaja is not None and self.precio_rebaja <= 0:
            self.precio_rebaja = None

        super().save(*args, **kwargs)

        if es_nuevo and not self.codigo:
            codigo = f"P-{self.pk:04d}"
            Producto.objects.filter(pk=self.pk).update(codigo=codigo)
            self.codigo = codigo


class ImagenProducto(models.Model):
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="imagenes",
    )
    imagen = models.TextField()
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "productos_imagenes"
        ordering = ["orden", "id"]

    def __str__(self):
        return f"Imagen {self.id} - {self.producto.titulo}"


class VarianteProducto(models.Model):
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="variantes",
    )
    color = models.CharField(max_length=80)
    talla = models.CharField(max_length=30)
    stock = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "productos_variantes"
        ordering = ["color", "talla"]
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "color", "talla"],
                name="unique_producto_color_talla",
            )
        ]

    def __str__(self):
        return f"{self.producto.titulo} - {self.color} / {self.talla}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.producto.sincronizar_disponibilidad(forzar_activo=self.stock > 0)

    def delete(self, *args, **kwargs):
        producto = self.producto
        super().delete(*args, **kwargs)
        producto.sincronizar_disponibilidad()