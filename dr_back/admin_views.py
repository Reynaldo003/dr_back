from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_auth import AdminAuthentication, IsAdminPanelUser, generar_token_admin
from .admin_serializers import AdminLoginSerializer, AdminMeSerializer


class AdminLoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier = serializer.validated_data["identifier"].strip()
        password = serializer.validated_data["password"]

        user = (
            User.objects.filter(
                Q(username__iexact=identifier) | Q(email__iexact=identifier)
            )
            .order_by("id")
            .first()
        )

        if not user or not user.check_password(password):
            return Response(
                {"detail": "Usuario o contraseña incorrectos."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not (user.is_staff or user.is_superuser):
            return Response(
                {"detail": "Ese usuario no tiene acceso al panel administrativo."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token = generar_token_admin(user)

        return Response(
            {
                "token": token,
                "user": AdminMeSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class AdminMeAPIView(APIView):
    authentication_classes = [AdminAuthentication]
    permission_classes = [IsAdminPanelUser]

    def get(self, request):
        return Response(AdminMeSerializer(request.user).data)


class AdminLogoutAPIView(APIView):
    authentication_classes = [AdminAuthentication]
    permission_classes = [IsAdminPanelUser]

    def post(self, request):
        return Response({"ok": True}, status=status.HTTP_200_OK)