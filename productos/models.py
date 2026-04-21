#productos/models.py
from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce


class Producto(models.Model):
    ESTADOS = (
        ("Activo", "Activo"),
        ("Inactivo", "Inactivo"),
    )

    codigo = models.CharField(max_length=20, unique=True, blank=True)
    titulo = models.CharField(max_length=200, db_index=True)
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
    categoria = models.CharField(max_length=100, blank=True, default="", db_index=True)
    estado = models.CharField(
        max_length=10,
        choices=ESTADOS,
        default="Activo",
        db_index=True,
    )
    imagen_principal = models.TextField(blank=True, default="")
    stock_vendido = models.PositiveIntegerField(default=0)

    es_new_arrival = models.BooleanField(default=False, db_index=True)
    permite_compra = models.BooleanField(default=True, db_index=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True, db_index=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "productos"
        ordering = ["-id"]
        indexes = [
            models.Index(
                fields=["estado", "es_new_arrival", "permite_compra"],
                name="idx_prod_estado_flags",
            ),
            models.Index(
                fields=["estado", "categoria"],
                name="idx_prod_estado_categoria",
            ),
        ]

    def __str__(self):
        return f"{self.codigo or self.pk} - {self.titulo}"

    @property
    def stock_total(self):
        stock_anotado = getattr(self, "_stock_total", None)
        if stock_anotado is not None:
            return int(stock_anotado or 0)

        cache_prefetch = getattr(self, "_prefetched_objects_cache", {})
        variantes_prefetch = cache_prefetch.get("variantes")
        if variantes_prefetch is not None:
            return int(sum(int(v.stock or 0) for v in variantes_prefetch))

        total = self.variantes.aggregate(
            total=Coalesce(Sum("stock"), 0)
        ).get("total")
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
        indexes = [
            models.Index(fields=["producto", "orden"], name="idx_img_prod_orden"),
        ]

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
        indexes = [
            models.Index(fields=["producto", "stock"], name="idx_var_prod_stock"),
            models.Index(fields=["producto", "color"], name="idx_var_prod_color"),
            models.Index(fields=["producto", "talla"], name="idx_var_prod_talla"),
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