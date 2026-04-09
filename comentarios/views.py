from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Comentario
from .serializers import ComentarioListSerializer, ComentarioPublicCreateSerializer


class ComentarioPublicView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        comentarios = Comentario.objects.filter(estado=Comentario.ESTADO_APROBADO)

        product_id = request.query_params.get("productId")
        if product_id not in (None, "", "null", "undefined"):
            comentarios = comentarios.filter(producto_id=product_id)

        serializer = ComentarioListSerializer(comentarios, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ComentarioPublicCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comentario = serializer.save()

        return Response(
            {
                "message": "Tu comentario fue enviado a revisión.",
                "comment": ComentarioListSerializer(comentario).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ComentarioAdminListView(APIView):
    # temporal: abierto mientras conectas login/roles
    permission_classes = [AllowAny]

    def get(self, request):
        comentarios = Comentario.objects.all()

        estado = request.query_params.get("estado")
        if estado and estado != "TODOS":
            comentarios = comentarios.filter(estado=estado)

        product_id = request.query_params.get("productId")
        if product_id not in (None, "", "null", "undefined"):
            comentarios = comentarios.filter(producto_id=product_id)

        q = (request.query_params.get("q") or "").strip()
        if q:
            comentarios = comentarios.filter(
                Q(nombre__icontains=q)
                | Q(comentario__icontains=q)
                | Q(producto_nombre__icontains=q)
            )

        serializer = ComentarioListSerializer(comentarios, many=True)

        stats = {
            "total": Comentario.objects.count(),
            "pendientes": Comentario.objects.filter(
                estado=Comentario.ESTADO_PENDIENTE
            ).count(),
            "aprobados": Comentario.objects.filter(
                estado=Comentario.ESTADO_APROBADO
            ).count(),
            "rechazados": Comentario.objects.filter(
                estado=Comentario.ESTADO_RECHAZADO
            ).count(),
        }

        return Response(
            {
                "results": serializer.data,
                "stats": stats,
            }
        )


class ComentarioAprobarView(APIView):
    # temporal: abierto mientras conectas login/roles
    permission_classes = [AllowAny]

    def post(self, request, pk):
        comentario = get_object_or_404(Comentario, pk=pk)
        comentario.estado = Comentario.ESTADO_APROBADO
        comentario.revisado_en = timezone.now()
        comentario.save(update_fields=["estado", "revisado_en", "actualizado_en"])

        return Response(
            {
                "message": "Comentario aprobado correctamente.",
                "comment": ComentarioListSerializer(comentario).data,
            }
        )


class ComentarioRechazarView(APIView):
    # temporal: abierto mientras conectas login/roles
    permission_classes = [AllowAny]

    def post(self, request, pk):
        comentario = get_object_or_404(Comentario, pk=pk)
        comentario.estado = Comentario.ESTADO_RECHAZADO
        comentario.revisado_en = timezone.now()
        comentario.save(update_fields=["estado", "revisado_en", "actualizado_en"])

        return Response(
            {
                "message": "Comentario rechazado correctamente.",
                "comment": ComentarioListSerializer(comentario).data,
            }
        )