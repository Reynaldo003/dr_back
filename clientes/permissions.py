from rest_framework.permissions import BasePermission

from .models import Cliente


class IsClienteAuthenticated(BasePermission):
    message = "Debes iniciar sesión como cliente."

    def has_permission(self, request, view):
        return bool(
            getattr(request, "user", None)
            and isinstance(request.user, Cliente)
            and request.user.activo
        )