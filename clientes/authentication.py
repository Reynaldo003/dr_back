from django.core import signing
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import Cliente

TOKEN_SALT = "clientes-auth"
TOKEN_MAX_AGE = 60 * 60 * 24 * 30  # 30 días


def generar_token_cliente(cliente: Cliente) -> str:
    payload = {
        "cliente_id": cliente.id,
        "token_version": cliente.token_version,
    }
    return signing.dumps(payload, salt=TOKEN_SALT)


def obtener_cliente_desde_token(token: str) -> Cliente:
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        raise AuthenticationFailed("Token de cliente inválido.")
    except signing.SignatureExpired:
        raise AuthenticationFailed("Tu sesión de cliente expiró.")

    cliente_id = payload.get("cliente_id")
    token_version = payload.get("token_version")

    cliente = Cliente.objects.filter(
        id=cliente_id,
        activo=True,
        token_version=token_version,
    ).first()

    if not cliente:
        raise AuthenticationFailed("La sesión del cliente ya no es válida.")

    return cliente


class ClienteAuthentication(BaseAuthentication):
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
        cliente = obtener_cliente_desde_token(token)
        return (cliente, None)