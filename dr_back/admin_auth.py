from django.contrib.auth.models import User
from django.core import signing
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

ADMIN_TOKEN_SALT = "admin-panel-auth"
ADMIN_TOKEN_MAX_AGE = 60 * 60 * 12  # 12 horas


def generar_token_admin(user: User) -> str:
    payload = {
        "user_id": user.id,
        "password_hash": user.password,
        "is_staff": bool(user.is_staff),
        "is_superuser": bool(user.is_superuser),
    }
    return signing.dumps(payload, salt=ADMIN_TOKEN_SALT)


def obtener_admin_desde_token(token: str) -> User:
    try:
        payload = signing.loads(
            token,
            salt=ADMIN_TOKEN_SALT,
            max_age=ADMIN_TOKEN_MAX_AGE,
        )
    except signing.SignatureExpired:
        raise AuthenticationFailed("La sesión administrativa expiró.")
    except signing.BadSignature:
        raise AuthenticationFailed("Token administrativo inválido.")

    user = User.objects.filter(
        id=payload.get("user_id"),
        is_active=True,
    ).first()

    if not user:
        raise AuthenticationFailed("Usuario administrativo no encontrado.")

    if not (user.is_staff or user.is_superuser):
        raise AuthenticationFailed("No tienes acceso al panel administrativo.")

    if payload.get("password_hash") != user.password:
        raise AuthenticationFailed("La sesión administrativa ya no es válida.")

    return user


class AdminAuthentication(BaseAuthentication):
    keyword = "bearer"

    def authenticate(self, request):
        header = get_authorization_header(request).split()

        if not header:
            return None

        if header[0].decode("utf-8").lower() != self.keyword:
            return None

        if len(header) != 2:
            raise AuthenticationFailed("Authorization inválido.")

        token = header[1].decode("utf-8")
        user = obtener_admin_desde_token(token)
        return (user, None)


class IsAdminPanelUser(BasePermission):
    message = "Debes iniciar sesión con un usuario administrativo."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(
            user
            and isinstance(user, User)
            and user.is_active
            and (user.is_staff or user.is_superuser)
        )