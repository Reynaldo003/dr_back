from django.contrib import admin
from .models import Comentario


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "producto_nombre", "estrellas", "estado", "creado_en", "revisado_en")
    list_filter = ("estado", "estrellas", "creado_en")
    search_fields = ("nombre", "comentario", "producto_nombre")
    ordering = ("-creado_en",)