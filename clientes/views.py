from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from dr_back.admin_auth import AdminAuthentication, IsAdminPanelUser
from ventas.models import Venta

from .authentication import ClienteAuthentication, generar_token_cliente
from .models import Cliente, ClienteDireccion, ClienteTarjeta
from .permissions import IsClienteAuthenticated
from .serializers import (
    AdminClienteListSerializer,
    ClienteDireccionSerializer,
    ClienteLoginSerializer,
    ClienteMeSerializer,
    ClientePedidoSerializer,
    ClienteRegistroSerializer,
    ClienteTarjetaSerializer,
)


class ClienteRegistroAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ClienteRegistroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cliente = serializer.save()
        token = generar_token_cliente(cliente)

        return Response(
            {
                "token": token,
                "cliente": ClienteMeSerializer(cliente).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ClienteLoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ClienteLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]

        cliente = Cliente.objects.filter(email__iexact=email, activo=True).first()

        if not cliente or not cliente.check_password(password):
            return Response(
                {"detail": "Correo o contraseña incorrectos."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token = generar_token_cliente(cliente)

        return Response(
            {
                "token": token,
                "cliente": ClienteMeSerializer(cliente).data,
            },
            status=status.HTTP_200_OK,
        )


class ClienteLogoutAPIView(APIView):
    authentication_classes = [ClienteAuthentication]
    permission_classes = [IsClienteAuthenticated]

    def post(self, request):
        return Response({"ok": True}, status=status.HTTP_200_OK)


class ClienteMeAPIView(APIView):
    authentication_classes = [ClienteAuthentication]
    permission_classes = [IsClienteAuthenticated]

    def get(self, request):
        return Response(ClienteMeSerializer(request.user).data)

    def patch(self, request):
        serializer = ClienteMeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ClienteDireccionViewSet(viewsets.ModelViewSet):
    serializer_class = ClienteDireccionSerializer
    authentication_classes = [ClienteAuthentication]
    permission_classes = [IsClienteAuthenticated]

    def get_queryset(self):
        return ClienteDireccion.objects.filter(cliente=self.request.user).order_by("-principal", "-id")

    def perform_create(self, serializer):
        destinatario = serializer.validated_data.get("destinatario", "").strip()
        telefono = serializer.validated_data.get("telefono", "").strip()

        if not destinatario:
            serializer.validated_data["destinatario"] = self.request.user.nombre

        if not telefono and self.request.user.telefono:
            serializer.validated_data["telefono"] = self.request.user.telefono

        serializer.save(cliente=self.request.user)


class ClienteTarjetaViewSet(viewsets.ModelViewSet):
    serializer_class = ClienteTarjetaSerializer
    authentication_classes = [ClienteAuthentication]
    permission_classes = [IsClienteAuthenticated]

    def get_queryset(self):
        return ClienteTarjeta.objects.filter(cliente=self.request.user).order_by("-principal", "-id")

    def perform_create(self, serializer):
        serializer.save(cliente=self.request.user)


class ClienteMisPedidosAPIView(APIView):
    authentication_classes = [ClienteAuthentication]
    permission_classes = [IsClienteAuthenticated]

    def get(self, request):
        queryset = (
            Venta.objects
            .filter(cliente_usuario=request.user)
            .prefetch_related("detalles__producto")
            .order_by("-id")
        )

        estado = request.query_params.get("estado", "").strip().upper()
        if estado:
            queryset = queryset.filter(estado=estado)

        serializer = ClientePedidoSerializer(queryset, many=True)
        return Response(serializer.data)


class ClienteMiPedidoDetalleAPIView(APIView):
    authentication_classes = [ClienteAuthentication]
    permission_classes = [IsClienteAuthenticated]

    def get(self, request, venta_id):
        venta = get_object_or_404(
            Venta.objects.prefetch_related("detalles__producto"),
            id=venta_id,
            cliente_usuario=request.user,
        )
        return Response(ClientePedidoSerializer(venta).data)


class AdminClienteViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AdminClienteListSerializer
    authentication_classes = [AdminAuthentication]
    permission_classes = [IsAdminPanelUser]

    def get_queryset(self):
        queryset = (
            Cliente.objects
            .prefetch_related("direcciones", "ventas")
            .order_by("-id")
        )

        q = self.request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(nombre__icontains=q)
                | Q(email__icontains=q)
                | Q(telefono__icontains=q)
                | Q(direcciones__direccion_linea1__icontains=q)
                | Q(direcciones__ciudad__icontains=q)
            ).distinct()

        return queryset