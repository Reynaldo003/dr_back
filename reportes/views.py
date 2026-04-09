import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.http import HttpResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from clientes.models import Cliente
from dr_back.admin_auth import AdminAuthentication, IsAdminPanelUser
from productos.models import Producto
from ventas.models import Venta


LOW_STOCK_LIMIT = 5


def _parse_date(value, field_name):
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field_name} debe venir en formato YYYY-MM-DD.")


def _normalizar_tipo(tipo):
    valor = str(tipo or "").strip().lower()

    if valor in ("ventas",):
        return "ventas"

    if valor in ("inventario",):
        return "inventario"

    if valor in ("low stock", "low_stock", "low-stock", "bajo stock", "bajo_stock"):
        return "low_stock"

    return "ventas"


def _stock_disponible_producto(producto):
    """
    stock_disponible no existe como campo real en BD.
    En tu proyecto se usa como propiedad calculada del modelo.
    Por eso aquí se lee en Python y no en queryset/order_by/filter de Django.
    """
    try:
        return int(getattr(producto, "stock_disponible", 0) or 0)
    except Exception:
        return 0


def _serializar_venta_minima(venta):
    return {
        "id": venta.id,
        "folio": venta.folio,
        "fecha_venta": str(venta.fecha_venta or ""),
        "cliente": venta.cliente or "",
        "cliente_email": venta.cliente_email or "",
        "cliente_telefono": venta.cliente_telefono or "",
        "estado": venta.estado or "",
        "metodo_pago": venta.metodo_pago or "",
        "total": float(venta.total or 0),
    }


def _obtener_rango_dashboard(modo, fecha_base):
    modo = str(modo or "day").strip().lower()

    if modo == "week":
        inicio = fecha_base - timedelta(days=6)
        fin = fecha_base
        return inicio, fin

    if modo == "month":
        inicio = fecha_base.replace(day=1)
        fin = fecha_base
        return inicio, fin

    inicio = fecha_base
    fin = fecha_base
    return inicio, fin


def _obtener_low_stock_queryset():
    productos = list(
        Producto.objects.all().order_by("titulo", "id")
    )

    low_stock = []
    for producto in productos:
        disponible = _stock_disponible_producto(producto)

        if disponible <= LOW_STOCK_LIMIT:
            low_stock.append(
                {
                    "id": producto.id,
                    "titulo": producto.titulo,
                    "codigo": getattr(producto, "codigo", "") or "",
                    "sku": getattr(producto, "sku", "") or "",
                    "categoria": getattr(producto, "categoria", "") or "",
                    "estado": getattr(producto, "estado", "") or "",
                    "stock_disponible": disponible,
                }
            )

    low_stock.sort(key=lambda x: (x["stock_disponible"], x["titulo"].lower()))
    return low_stock


def _filas_ventas(desde=None, hasta=None):
    queryset = Venta.objects.prefetch_related("detalles__producto").order_by("-fecha_venta", "-id")

    if desde:
        queryset = queryset.filter(fecha_venta__gte=desde)

    if hasta:
        queryset = queryset.filter(fecha_venta__lte=hasta)

    filas = []
    for venta in queryset:
        productos = ", ".join(
            [
                f"{d.producto.titulo} x{d.cantidad}"
                for d in venta.detalles.all()
            ]
        )

        filas.append(
            {
                "Folio": venta.folio,
                "Fecha": str(venta.fecha_venta or ""),
                "Cliente": venta.cliente or "",
                "Correo": venta.cliente_email or "",
                "Telefono": venta.cliente_telefono or "",
                "Ciudad": venta.ciudad or "",
                "Estado direccion": venta.estado_direccion or "",
                "Estado venta": venta.estado or "",
                "Estado envio": venta.estado_envio or "",
                "Metodo pago": venta.metodo_pago or "",
                "Total": float(venta.total or 0),
                "Productos": productos,
            }
        )

    return filas


def _filas_inventario():
    queryset = Producto.objects.all().order_by("titulo", "id")

    filas = []
    for producto in queryset:
        filas.append(
            {
                "ID": producto.id,
                "Producto": producto.titulo,
                "Codigo": getattr(producto, "codigo", "") or "",
                "SKU": getattr(producto, "sku", "") or "",
                "Categoria": getattr(producto, "categoria", "") or "",
                "Precio": float(getattr(producto, "precio", 0) or 0),
                "Estado": getattr(producto, "estado", "") or "",
                "Stock vendido": int(getattr(producto, "stock_vendido", 0) or 0),
                "Stock disponible": _stock_disponible_producto(producto),
            }
        )

    return filas


def _filas_low_stock():
    low_stock = _obtener_low_stock_queryset()

    filas = []
    for item in low_stock:
        filas.append(
            {
                "ID": item["id"],
                "Producto": item["titulo"],
                "Codigo": item["codigo"],
                "SKU": item["sku"],
                "Categoria": item["categoria"],
                "Estado": item["estado"],
                "Stock disponible": item["stock_disponible"],
            }
        )

    return filas


def _obtener_filas(tipo, desde=None, hasta=None):
    tipo_n = _normalizar_tipo(tipo)

    if tipo_n == "inventario":
        return _filas_inventario()

    if tipo_n == "low_stock":
        return _filas_low_stock()

    return _filas_ventas(desde=desde, hasta=hasta)


@api_view(["GET"])
@authentication_classes([AdminAuthentication])
@permission_classes([IsAdminPanelUser])
def dashboard_resumen(request):
    modo = request.query_params.get("modo", "day")
    fecha_base_raw = request.query_params.get("fecha_base", "")

    try:
        fecha_base = (
            _parse_date(fecha_base_raw, "fecha_base")
            if fecha_base_raw
            else datetime.now().date()
        )
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)

    desde, hasta = _obtener_rango_dashboard(modo, fecha_base)

    ventas_qs = (
        Venta.objects
        .filter(fecha_venta__gte=desde, fecha_venta__lte=hasta)
        .order_by("-fecha_venta", "-id")
    )

    total_ordenes = ventas_qs.count()
    ordenes_pagadas = ventas_qs.filter(estado="PAGADA").count()

    total_ventas_decimal = (
        ventas_qs.filter(estado="PAGADA").aggregate(total=Sum("total"))["total"]
        or Decimal("0.00")
    )

    ticket_promedio = (
        float(total_ventas_decimal) / ordenes_pagadas
        if ordenes_pagadas > 0
        else 0
    )

    resumen_estados_qs = (
        ventas_qs.values("estado")
        .annotate(cantidad=Count("id"), total=Sum("total"))
        .order_by("estado")
    )

    resumen_estados = [
        {
            "estado": row["estado"],
            "cantidad": row["cantidad"],
            "total": float(row["total"] or 0),
        }
        for row in resumen_estados_qs
    ]

    ventas = [_serializar_venta_minima(v) for v in ventas_qs[:50]]
    low_stock = _obtener_low_stock_queryset()[:20]

    return Response(
        {
            "modo": str(modo or "day").lower(),
            "fecha_base": str(fecha_base),
            "desde": str(desde),
            "hasta": str(hasta),
            "total_ordenes": total_ordenes,
            "total_ventas": float(total_ventas_decimal),
            "ordenes_pagadas": ordenes_pagadas,
            "ticket_promedio": float(ticket_promedio),
            "resumen_estados": resumen_estados,
            "low_stock": low_stock,
            "ventas": ventas,
            "clientes_registrados": Cliente.objects.count(),
        }
    )


@api_view(["GET"])
@authentication_classes([AdminAuthentication])
@permission_classes([IsAdminPanelUser])
def reporte_preview(request):
    tipo = request.query_params.get("tipo", "Ventas")
    desde_raw = request.query_params.get("desde", "")
    hasta_raw = request.query_params.get("hasta", "")

    try:
        desde = _parse_date(desde_raw, "desde")
        hasta = _parse_date(hasta_raw, "hasta")
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)

    if desde and hasta and desde > hasta:
        return Response({"detail": "El rango de fechas es inválido."}, status=400)

    filas = _obtener_filas(tipo=tipo, desde=desde, hasta=hasta)

    return Response(
        {
            "tipo": tipo,
            "desde": str(desde) if desde else "",
            "hasta": str(hasta) if hasta else "",
            "total_registros": len(filas),
            "filas": filas,
        }
    )


def _exportar_csv(filas, filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    if not filas:
        writer.writerow(["Sin datos"])
        return response

    headers = list(filas[0].keys())
    writer.writerow(headers)

    for fila in filas:
        writer.writerow([fila.get(h, "") for h in headers])

    return response


def _exportar_excel(filas, filename):
    try:
        from openpyxl import Workbook
    except ImportError:
        return Response(
            {"detail": "Instala openpyxl para exportar Excel."},
            status=400,
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "Reporte"

    if not filas:
        ws.append(["Sin datos"])
    else:
        headers = list(filas[0].keys())
        ws.append(headers)

        for fila in filas:
            ws.append([fila.get(h, "") for h in headers])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _exportar_pdf(filas, filename, titulo):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        return Response(
            {"detail": "Instala reportlab para exportar PDF."},
            status=400,
        )

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    y = height - 40
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, titulo)
    y -= 24

    pdf.setFont("Helvetica", 9)

    if not filas:
        pdf.drawString(40, y, "Sin datos para exportar.")
    else:
        for fila in filas:
            texto = " | ".join([f"{k}: {fila.get(k, '')}" for k in fila.keys()])
            lineas = [texto[i:i + 110] for i in range(0, len(texto), 110)]

            for linea in lineas:
                if y < 40:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 9)
                    y = height - 40

                pdf.drawString(40, y, linea)
                y -= 14

            y -= 6

    pdf.save()
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@api_view(["GET"])
@authentication_classes([AdminAuthentication])
@permission_classes([IsAdminPanelUser])
def exportar_reporte(request):
    tipo = request.query_params.get("tipo", "Ventas")
    formato = str(request.query_params.get("formato", "PDF") or "PDF").strip().lower()
    desde_raw = request.query_params.get("desde", "")
    hasta_raw = request.query_params.get("hasta", "")

    try:
        desde = _parse_date(desde_raw, "desde")
        hasta = _parse_date(hasta_raw, "hasta")
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)

    if desde and hasta and desde > hasta:
        return Response({"detail": "El rango de fechas es inválido."}, status=400)

    filas = _obtener_filas(tipo=tipo, desde=desde, hasta=hasta)
    tipo_slug = _normalizar_tipo(tipo)

    if formato == "csv":
      return _exportar_csv(filas, f"reporte_{tipo_slug}.csv")

    if formato == "excel":
      return _exportar_excel(filas, f"reporte_{tipo_slug}.xlsx")

    if formato == "pdf":
      return _exportar_pdf(filas, f"reporte_{tipo_slug}.pdf", f"Reporte {tipo}")

    return Response({"detail": "Formato no soportado."}, status=400)