import csv
import io
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from productos.models import Producto
from ventas.models import Venta


ESTADOS_VENTA_VALIDOS = ["PAGADA", "PENDIENTE", "CANCELADA", "REEMBOLSADA"]


def obtener_ventas_filtradas(desde=None, hasta=None):
    queryset = Venta.objects.prefetch_related("detalles__producto").all().order_by("-fecha_venta", "-id")

    if desde:
        queryset = queryset.filter(fecha_venta__gte=desde)

    if hasta:
        queryset = queryset.filter(fecha_venta__lte=hasta)

    return queryset


def construir_dashboard(periodo, fecha_base):
    ventas = obtener_ventas_filtradas(*periodo)

    total_ventas = ventas.aggregate(
        total=Coalesce(Sum("total"), Decimal("0.00"))
    )["total"]

    total_ordenes = ventas.count()

    ventas_pagadas = ventas.filter(estado="PAGADA")
    total_pagadas = ventas_pagadas.aggregate(
        total=Coalesce(Sum("total"), Decimal("0.00"))
    )["total"]

    ordenes_pagadas = ventas_pagadas.count()
    ticket_promedio = Decimal("0.00")

    if ordenes_pagadas > 0:
        ticket_promedio = total_pagadas / ordenes_pagadas

    resumen_estados_qs = (
        ventas.values("estado")
        .annotate(
            total=Coalesce(Sum("total"), Decimal("0.00")),
            cantidad=Count("id"),
        )
        .order_by("estado")
    )

    resumen_estados = []
    mapa_estados = {item["estado"]: item for item in resumen_estados_qs}

    for estado in ESTADOS_VENTA_VALIDOS:
        item = mapa_estados.get(estado)
        resumen_estados.append({
            "estado": estado,
            "cantidad": int(item["cantidad"]) if item else 0,
            "total": str(item["total"]) if item else "0.00",
        })

    ventas_lista = []
    for venta in ventas:
        ventas_lista.append({
            "id": venta.id,
            "folio": venta.folio,
            "fecha_venta": str(venta.fecha_venta),
            "cliente": venta.cliente,
            "estado": venta.estado,
            "metodo_pago": venta.metodo_pago,
            "total": str(venta.total),
        })

    productos_low_stock = []
    for producto in Producto.objects.all().order_by("titulo"):
        if producto.stock_disponible <= 5:
            productos_low_stock.append({
                "id": producto.id,
                "codigo": producto.codigo,
                "titulo": producto.titulo,
                "sku": producto.sku,
                "stock_disponible": producto.stock_disponible,
            })

    return {
        "fecha_base": str(fecha_base),
        "total_ventas": str(total_ventas),
        "total_ordenes": total_ordenes,
        "total_pagadas": str(total_pagadas),
        "ordenes_pagadas": ordenes_pagadas,
        "ticket_promedio": str(ticket_promedio.quantize(Decimal("0.01"))),
        "resumen_estados": resumen_estados,
        "ventas": ventas_lista,
        "low_stock": productos_low_stock,
    }


def construir_reporte_ventas(desde=None, hasta=None):
    ventas = obtener_ventas_filtradas(desde, hasta)

    filas = []
    total = Decimal("0.00")

    for venta in ventas:
        filas.append({
            "folio": venta.folio,
            "fecha": str(venta.fecha_venta),
            "cliente": venta.cliente,
            "estado": venta.estado,
            "metodo_pago": venta.metodo_pago,
            "subtotal": str(venta.subtotal),
            "total": str(venta.total),
        })
        total += venta.total

    return {
        "tipo": "Ventas",
        "desde": str(desde) if desde else "",
        "hasta": str(hasta) if hasta else "",
        "total_registros": len(filas),
        "total_general": str(total),
        "filas": filas,
    }


def construir_reporte_inventario():
    filas = []

    for producto in Producto.objects.prefetch_related("variantes").all().order_by("titulo"):
        filas.append({
            "codigo": producto.codigo,
            "titulo": producto.titulo,
            "sku": producto.sku,
            "categoria": producto.categoria,
            "estado": producto.estado,
            "precio": str(producto.precio),
            "stock_total": producto.stock_total,
            "stock_vendido": producto.stock_vendido,
            "stock_disponible": producto.stock_disponible,
        })

    return {
        "tipo": "Inventario",
        "total_registros": len(filas),
        "filas": filas,
    }


def construir_reporte_low_stock():
    filas = []

    for producto in Producto.objects.prefetch_related("variantes").all().order_by("stock_vendido", "titulo"):
        if producto.stock_disponible <= 5:
            filas.append({
                "codigo": producto.codigo,
                "titulo": producto.titulo,
                "sku": producto.sku,
                "categoria": producto.categoria,
                "estado": producto.estado,
                "stock_disponible": producto.stock_disponible,
            })

    return {
        "tipo": "Low stock",
        "total_registros": len(filas),
        "filas": filas,
    }


def construir_reporte(tipo, desde=None, hasta=None):
    if tipo == "Ventas":
        return construir_reporte_ventas(desde, hasta)

    if tipo == "Inventario":
        return construir_reporte_inventario()

    if tipo == "Low stock":
        return construir_reporte_low_stock()

    raise ValueError("Tipo de reporte no válido.")


def exportar_csv(data, nombre_archivo):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}.csv"'

    writer = csv.writer(response)
    filas = data.get("filas", [])

    if not filas:
        writer.writerow(["Sin datos"])
        return response

    headers = list(filas[0].keys())
    writer.writerow(headers)

    for fila in filas:
        writer.writerow([fila.get(header, "") for header in headers])

    return response


def exportar_excel(data, nombre_archivo):
    wb = Workbook()
    ws = wb.active
    ws.title = data.get("tipo", "Reporte")

    filas = data.get("filas", [])

    if filas:
        headers = list(filas[0].keys())
        ws.append(headers)

        for fila in filas:
            ws.append([fila.get(header, "") for header in headers])
    else:
        ws.append(["Sin datos"])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}.xlsx"'
    return response


def exportar_pdf(data, nombre_archivo):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 40
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, f"Reporte: {data.get('tipo', 'General')}")
    y -= 20

    pdf.setFont("Helvetica", 10)
    if data.get("desde") or data.get("hasta"):
        pdf.drawString(40, y, f"Rango: {data.get('desde', '')} a {data.get('hasta', '')}")
        y -= 20

    filas = data.get("filas", [])
    if not filas:
        pdf.drawString(40, y, "Sin datos.")
    else:
        headers = list(filas[0].keys())
        pdf.setFont("Helvetica-Bold", 9)
        x_positions = [40, 120, 220, 320, 420, 500]

        for i, header in enumerate(headers[:6]):
            pdf.drawString(x_positions[i], y, str(header)[:18])

        y -= 16
        pdf.setFont("Helvetica", 8)

        for fila in filas:
            if y < 50:
                pdf.showPage()
                y = height - 40

            for i, header in enumerate(headers[:6]):
                valor = str(fila.get(header, ""))[:22]
                pdf.drawString(x_positions[i], y, valor)

            y -= 14

    pdf.showPage()
    pdf.save()

    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}.pdf"'
    return response