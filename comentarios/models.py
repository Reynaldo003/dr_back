from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from productos.models import Producto


class Comentario(models.Model):
    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_APROBADO = "APROBADO"
    ESTADO_RECHAZADO = "RECHAZADO"

    ESTADOS = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_APROBADO, "Aprobado"),
        (ESTADO_RECHAZADO, "Rechazado"),
    ]

    producto = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comentarios",
    )
    producto_nombre = models.CharField(max_length=255, blank=True, default="")
    nombre = models.CharField(max_length=120)
    estrellas = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comentario = models.TextField()
    estado = models.CharField(
        max_length=12,
        choices=ESTADOS,
        default=ESTADO_PENDIENTE,
        db_index=True,
    )
    revisado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "comentarios"
        ordering = ["-creado_en"]

    def __str__(self):
        producto = self.producto_nombre or "Boutique"
        return f"{self.nombre} - {producto} - {self.estado}"

    def save(self, *args, **kwargs):
        if self.producto and not self.producto_nombre:
            self.producto_nombre = getattr(self.producto, "titulo", "") or ""
        super().save(*args, **kwargs)