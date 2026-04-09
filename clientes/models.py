from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class Cliente(models.Model):
    nombre = models.CharField(max_length=180)
    email = models.EmailField(unique=True, db_index=True)
    telefono = models.CharField(max_length=30, blank=True, default="")
    password = models.CharField(max_length=128)

    activo = models.BooleanField(default=True)
    email_verificado = models.BooleanField(default=False)
    token_version = models.PositiveIntegerField(default=1)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clientes"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.nombre} <{self.email}>"

    @property
    def is_authenticated(self):
        return True

    def set_password(self, raw_password: str):
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)


class ClienteDireccion(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="direcciones",
    )
    alias = models.CharField(max_length=80, blank=True, default="")
    destinatario = models.CharField(max_length=180, blank=True, default="")
    telefono = models.CharField(max_length=30, blank=True, default="")

    direccion_linea1 = models.CharField(max_length=255)
    direccion_linea2 = models.CharField(max_length=255, blank=True, default="")
    ciudad = models.CharField(max_length=120)
    estado_direccion = models.CharField(max_length=120)
    codigo_postal = models.CharField(max_length=20, blank=True, default="")
    referencias_envio = models.TextField(blank=True, default="")

    principal = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clientes_direcciones"
        ordering = ["-principal", "-id"]

    def __str__(self):
        alias = self.alias or "Dirección"
        return f"{self.cliente.email} - {alias}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.principal:
            ClienteDireccion.objects.filter(cliente=self.cliente).exclude(pk=self.pk).update(principal=False)


class ClienteTarjeta(models.Model):
    PROVEEDORES = (
        ("MERCADO_PAGO", "Mercado Pago"),
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="tarjetas",
    )
    proveedor = models.CharField(max_length=40, choices=PROVEEDORES, default="MERCADO_PAGO")

    titular = models.CharField(max_length=180, blank=True, default="")
    marca = models.CharField(max_length=50, blank=True, default="")
    ultimos4 = models.CharField(max_length=4)
    mes_expiracion = models.PositiveSmallIntegerField(null=True, blank=True)
    anio_expiracion = models.PositiveSmallIntegerField(null=True, blank=True)

    mp_customer_id = models.CharField(max_length=120, blank=True, default="")
    mp_card_id = models.CharField(max_length=120, blank=True, default="")

    principal = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clientes_tarjetas"
        ordering = ["-principal", "-id"]
        unique_together = [("cliente", "mp_card_id")]

    def __str__(self):
        return f"{self.cliente.email} - **** {self.ultimos4}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.principal:
            ClienteTarjeta.objects.filter(cliente=self.cliente).exclude(pk=self.pk).update(principal=False)