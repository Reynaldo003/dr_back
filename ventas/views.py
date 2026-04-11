from django.db import transaction
from django.db.models import Prefetch, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from clientes.authentication import ClienteAuthentication
from dr_back.admin_auth import AdminAuthentication, IsAdminPanelUser

from .models import Venta, VentaDetalle
from .serializers import CheckoutMercadoPagoSerializer, VentaSerializer
from .services import (
    MercadoPagoError,
    crear_preferencia_mercado_pago,
    descontar_inventario_si_aplica,
    procesar_webhook_pago,
    regresar_inventario_si_aplica,
    validar_firma_webhook,
)


class VentaViewSet(viewsets.ModelViewSet):
    serializer_class = VentaSerializer
    authentication_classes = [AdminAuthentication]
    permission_classes = [IsAdminPanelUser]

    queryset = (
        Venta.objects
        .select_related("cliente_usuario", "cliente_direccion")
        .prefetch_related(
            Prefetch(
                "detalles",
                queryset=VentaDetalle.objects.select_related("producto").order_by("id"),
            )
        )
        .all()
    )

    def get_queryset(self):
        queryset = self.queryset.defer("mp_raw").order_by("-id")

        q = self.request.query_params.get("q", "").strip()
        estado = self.request.query_params.get("estado", "").strip().upper()

        if q:
            queryset = queryset.filter(
                Q(cliente__icontains=q)
                | Q(cliente_email__icontains=q)
                | Q(cliente_telefono__icontains=q)
                | Q(folio__icontains=q)
                | Q(ciudad__icontains=q)
                | Q(estado_direccion__icontains=q)
            )

        if estado and estado != "TODOS":
            queryset = queryset.filter(estado=estado)

        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            venta = serializer.save()

            if venta.metodo_pago != "MERCADO_PAGO" and venta.estado == "PAGADA":
                descontar_inventario_si_aplica(venta)
        except MercadoPagoError as e:
            transaction.set_rollback(True)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        response_serializer = self.get_serializer(venta)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        venta = self.get_object()

        if venta.mp_payment_id:
            return Response(
                {"detail": "No puedes editar manualmente una venta ligada a un pago confirmado."},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            if venta.inventario_descontado:
                regresar_inventario_si_aplica(venta)
                venta.refresh_from_db()

            serializer = self.get_serializer(venta, data=request.data)
            serializer.is_valid(raise_exception=True)
            venta = serializer.save()

            if venta.metodo_pago != "MERCADO_PAGO" and venta.estado == "PAGADA":
                descontar_inventario_si_aplica(venta)
        except MercadoPagoError as e:
            transaction.set_rollback(True)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        response_serializer = self.get_serializer(venta)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        venta = self.get_object()

        if venta.mp_payment_id:
            return Response(
                {"detail": "No puedes editar manualmente una venta ligada a un pago confirmado."},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            if venta.inventario_descontado:
                regresar_inventario_si_aplica(venta)
                venta.refresh_from_db()

            serializer = self.get_serializer(venta, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            venta = serializer.save()

            if venta.metodo_pago != "MERCADO_PAGO" and venta.estado == "PAGADA":
                descontar_inventario_si_aplica(venta)
        except MercadoPagoError as e:
            transaction.set_rollback(True)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        response_serializer = self.get_serializer(venta)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        venta = self.get_object()

        if venta.mp_payment_id:
            return Response(
                {"detail": "No puedes eliminar una venta ligada a Mercado Pago. Debes cancelarla o reembolsarla."},
                status=status.HTTP_409_CONFLICT,
            )

        regresar_inventario_si_aplica(venta)
        venta.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def crear_preferencia(self, request, pk=None):
        venta = self.get_object()

        if venta.estado == "PAGADA":
            return Response(
                {"detail": "La venta ya está pagada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = crear_preferencia_mercado_pago(venta)
            return Response(data, status=status.HTTP_200_OK)
        except MercadoPagoError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CheckoutMercadoPagoAPIView(APIView):
    authentication_classes = [ClienteAuthentication]
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = CheckoutMercadoPagoSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            venta = serializer.save()
            preferencia = crear_preferencia_mercado_pago(venta)
        except MercadoPagoError as e:
            transaction.set_rollback(True)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "venta": VentaSerializer(venta).data,
                "preference_id": preferencia.get("id"),
                "init_point": preferencia.get("init_point"),
                "sandbox_init_point": preferencia.get("sandbox_init_point"),
            },
            status=status.HTTP_201_CREATED,
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def webhook_mercado_pago(request):
    if not validar_firma_webhook(request):
        return Response({"detail": "Firma inválida."}, status=status.HTTP_401_UNAUTHORIZED)

    body = request.data if isinstance(request.data, dict) else {}
    data = body.get("data", {})
    payment_id = data.get("id") or request.GET.get("data.id") or request.GET.get("id")

    if not payment_id:
        return Response({"detail": "No llegó payment_id."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        procesar_webhook_pago(str(payment_id))
    except Venta.DoesNotExist:
        return Response({"detail": "Venta no encontrada."}, status=status.HTTP_404_NOT_FOUND)
    except MercadoPagoError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": f"Error interno: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"ok": True}, status=status.HTTP_200_OK)