#ventas/services.py
import hashlib
import hmac
import uuid

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import F

from .models import Venta


class MercadoPagoError(Exception):
    pass


def generar_idempotency_key():
    return str(uuid.uuid4())


@transaction.atomic
def descontar_inventario_si_aplica(venta: Venta):
    if venta.inventario_descontado:
        return

    if venta.estado != "PAGADA":
        return

    for detalle in venta.detalles.select_related("producto").all():
        producto = detalle.producto.__class__.objects.select_for_update().get(pk=detalle.producto_id)

        if detalle.cantidad > producto.stock_disponible:
            raise MercadoPagoError(
                f"Stock insuficiente para {producto.titulo}. Disponible: {producto.stock_disponible}."
            )

        producto.stock_vendido = F("stock_vendido") + detalle.cantidad
        producto.save(update_fields=["stock_vendido"])

    venta.inventario_descontado = True
    venta.save(update_fields=["inventario_descontado"])


@transaction.atomic
def regresar_inventario_si_aplica(venta: Venta):
    if not venta.inventario_descontado:
        return

    for detalle in venta.detalles.select_related("producto").all():
        producto = detalle.producto.__class__.objects.select_for_update().get(pk=detalle.producto_id)
        nuevo_stock_vendido = max((producto.stock_vendido or 0) - detalle.cantidad, 0)
        producto.stock_vendido = nuevo_stock_vendido
        producto.save(update_fields=["stock_vendido"])

    venta.inventario_descontado = False
    venta.save(update_fields=["inventario_descontado"])


def crear_preferencia_mercado_pago(venta: Venta):
    access_token = getattr(settings, "MP_ACCESS_TOKEN", "").strip()
    back_url_success = getattr(settings, "MP_BACK_URL_SUCCESS", "").strip()
    back_url_pending = getattr(settings, "MP_BACK_URL_PENDING", "").strip()
    back_url_failure = getattr(settings, "MP_BACK_URL_FAILURE", "").strip()
    notification_url = getattr(settings, "MP_NOTIFICATION_URL", "").strip()

    if not access_token:
        raise MercadoPagoError("Falta configurar MP_ACCESS_TOKEN.")

    if not back_url_success:
        raise MercadoPagoError("Falta configurar MP_BACK_URL_SUCCESS.")

    if not back_url_pending:
        raise MercadoPagoError("Falta configurar MP_BACK_URL_PENDING.")

    if not back_url_failure:
        raise MercadoPagoError("Falta configurar MP_BACK_URL_FAILURE.")

    items = []
    for detalle in venta.detalles.select_related("producto").all():
        variante = " / ".join([v for v in [detalle.color, detalle.talla] if v]).strip()

        titulo = detalle.producto.titulo
        if variante:
            titulo = f"{titulo} - {variante}"

        items.append(
            {
                "title": titulo,
                "quantity": detalle.cantidad,
                "unit_price": float(detalle.precio_unitario),
                "currency_id": "MXN",
            }
        )

    payer = {"name": venta.cliente}
    if venta.cliente_email:
        payer["email"] = venta.cliente_email

    payload = {
        "items": items,
        "external_reference": str(venta.referencia_externa),
        "payer": payer,
        "metadata": {
            "venta_id": venta.id,
            "folio": venta.folio,
            "cliente_usuario_id": venta.cliente_usuario_id,
        },
        "back_urls": {
            "success": back_url_success,
            "pending": back_url_pending,
            "failure": back_url_failure,
        },
        "auto_return": "approved",
        "statement_descriptor": "DOSREYNAS",
    }

    if notification_url:
        payload["notification_url"] = notification_url

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": generar_idempotency_key(),
    }

    response = requests.post(
        "https://api.mercadopago.com/checkout/preferences",
        headers=headers,
        json=payload,
        timeout=30,
    )

    if response.status_code not in (200, 201):
        raise MercadoPagoError(f"Mercado Pago respondió con error: {response.text}")

    data = response.json()
    venta.mp_preference_id = data.get("id", "")
    venta.mp_raw = data
    venta.save(update_fields=["mp_preference_id", "mp_raw"])

    return data


def obtener_pago_mercado_pago(payment_id: str):
    access_token = getattr(settings, "MP_ACCESS_TOKEN", "").strip()

    if not access_token:
        raise MercadoPagoError("Falta configurar MP_ACCESS_TOKEN.")

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    response = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=headers,
        timeout=30,
    )

    if response.status_code != 200:
        raise MercadoPagoError(f"No se pudo consultar el pago: {response.text}")

    return response.json()


def validar_firma_webhook(request):
    secret = getattr(settings, "MP_WEBHOOK_SECRET", "").strip()

    if not secret:
        return bool(getattr(settings, "DEBUG", False))

    x_signature = request.headers.get("x-signature", "")
    x_request_id = request.headers.get("x-request-id", "")

    if not x_signature or not x_request_id:
        return False

    data_id = request.GET.get("data.id", "") or request.GET.get("id", "")
    raw_ts = ""
    raw_v1 = ""

    partes = [p.strip() for p in x_signature.split(",") if p.strip()]
    for parte in partes:
        if parte.startswith("ts="):
            raw_ts = parte.replace("ts=", "", 1)
        elif parte.startswith("v1="):
            raw_v1 = parte.replace("v1=", "", 1)

    if not raw_ts or not raw_v1 or not data_id:
        return False

    manifest = f"id:{data_id};request-id:{x_request_id};ts:{raw_ts};"

    firma = hmac.new(
        secret.encode("utf-8"),
        msg=manifest.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(firma, raw_v1)


@transaction.atomic
def procesar_webhook_pago(payment_id: str):
    data = obtener_pago_mercado_pago(payment_id)

    external_reference = data.get("external_reference")
    status = data.get("status", "")
    status_detail = data.get("status_detail", "")

    if not external_reference:
        raise MercadoPagoError("El pago no trae external_reference.")

    venta = Venta.objects.select_for_update().get(referencia_externa=external_reference)
    venta.mp_payment_id = str(data.get("id", ""))
    venta.mp_status = status
    venta.mp_status_detail = status_detail
    venta.mp_raw = data

    if status == "approved":
        venta.estado = "PAGADA"
        venta.save(update_fields=["mp_payment_id", "mp_status", "mp_status_detail", "mp_raw", "estado"])
        descontar_inventario_si_aplica(venta)
    elif status in ("rejected", "cancelled", "refunded", "charged_back"):
        venta.estado = "REEMBOLSADA" if status == "refunded" else "CANCELADA"
        venta.save(update_fields=["mp_payment_id", "mp_status", "mp_status_detail", "mp_raw", "estado"])
        regresar_inventario_si_aplica(venta)
    else:
        venta.save(update_fields=["mp_payment_id", "mp_status", "mp_status_detail", "mp_raw"])

    return venta