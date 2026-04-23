import base64
import io
import re

from PIL import Image, ImageOps, UnidentifiedImageError

DATA_URL_RE = re.compile(
    r"^data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$",
    re.DOTALL,
)

FORMATO_SALIDA = "WEBP"
MIME_SALIDA = "image/webp"


def es_data_url_imagen(valor):
    return bool(DATA_URL_RE.match(str(valor or "").strip()))


def _dividir_data_url(valor):
    match = DATA_URL_RE.match(str(valor or "").strip())
    if not match:
        return None, None

    mime = match.group("mime")
    data = match.group("data")
    return mime, data


def _decodificar_data_url(valor):
    mime, data = _dividir_data_url(valor)
    if not mime or not data:
        return None, None

    try:
        contenido = base64.b64decode(data)
    except Exception:
        return None, None

    return mime, contenido


def _normalizar_imagen(imagen):
    imagen = ImageOps.exif_transpose(imagen)

    if imagen.mode not in ("RGB", "RGBA"):
        if "A" in imagen.getbands():
            imagen = imagen.convert("RGBA")
        else:
            imagen = imagen.convert("RGB")

    return imagen


def _guardar_webp(imagen, quality):
    salida = io.BytesIO()
    imagen.save(
        salida,
        format=FORMATO_SALIDA,
        quality=int(quality),
        method=6,
    )
    return salida.getvalue()


def _a_data_url_webp(contenido):
    return f"data:{MIME_SALIDA};base64,{base64.b64encode(contenido).decode('utf-8')}"


def optimizar_data_url_imagen(
    valor,
    *,
    max_width=1600,
    max_height=1600,
    quality=82,
):
    valor = str(valor or "").strip()
    if not valor:
        return ""

    if not es_data_url_imagen(valor):
        return valor

    _, contenido = _decodificar_data_url(valor)
    if not contenido:
        return valor

    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            imagen = _normalizar_imagen(imagen)
            imagen.thumbnail((int(max_width), int(max_height)), Image.Resampling.LANCZOS)
            optimizada = _guardar_webp(imagen, quality)
    except (UnidentifiedImageError, OSError, ValueError):
        return valor

    resultado = _a_data_url_webp(optimizada)

    if len(resultado) >= len(valor):
        return valor

    return resultado


def preparar_imagen_principal(valor):
    original = optimizar_data_url_imagen(
        valor,
        max_width=1600,
        max_height=1600,
        quality=82,
    )
    thumb = optimizar_data_url_imagen(
        original,
        max_width=480,
        max_height=480,
        quality=72,
    )
    return original, thumb or original


def preparar_imagen_galeria(valor):
    original = optimizar_data_url_imagen(
        valor,
        max_width=1600,
        max_height=1600,
        quality=82,
    )
    thumb = optimizar_data_url_imagen(
        original,
        max_width=360,
        max_height=360,
        quality=70,
    )
    return original, thumb or original
