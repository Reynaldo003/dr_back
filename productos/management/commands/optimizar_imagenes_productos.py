from django.core.management.base import BaseCommand

from productos.image_utils import preparar_imagen_galeria, preparar_imagen_principal
from productos.models import ImagenProducto, Producto


class Command(BaseCommand):
    help = "Genera thumbnails para productos existentes y opcionalmente recompime originales base64."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reescribir-originales",
            action="store_true",
            dest="reescribir_originales",
            help="También recompime y reemplaza las imágenes originales base64.",
        )

    def handle(self, *args, **options):
        reescribir_originales = options["reescribir_originales"]

        self.stdout.write(self.style.NOTICE("Procesando productos..."))
        actualizados_productos = 0
        actualizadas_imagenes = 0

        for producto in Producto.objects.all().iterator(chunk_size=100):
            cambios = {}

            imagen_principal = str(producto.imagen_principal or "").strip()
            if imagen_principal.startswith("data:image/"):
                original, thumb = preparar_imagen_principal(imagen_principal)

                if reescribir_originales and original != producto.imagen_principal:
                    cambios["imagen_principal"] = original

                if thumb != (producto.imagen_principal_thumb or ""):
                    cambios["imagen_principal_thumb"] = thumb

            if cambios:
                Producto.objects.filter(pk=producto.pk).update(**cambios)
                actualizados_productos += 1

        self.stdout.write(self.style.NOTICE("Procesando galería..."))

        for imagen in ImagenProducto.objects.all().iterator(chunk_size=200):
            valor = str(imagen.imagen or "").strip()
            if not valor.startswith("data:image/"):
                continue

            original, thumb = preparar_imagen_galeria(valor)
            cambios = {}

            if reescribir_originales and original != imagen.imagen:
                cambios["imagen"] = original

            if thumb != (imagen.imagen_thumb or ""):
                cambios["imagen_thumb"] = thumb

            if cambios:
                ImagenProducto.objects.filter(pk=imagen.pk).update(**cambios)
                actualizadas_imagenes += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. Productos actualizados: {actualizados_productos}. "
                f"Imágenes de galería actualizadas: {actualizadas_imagenes}."
            )
        )