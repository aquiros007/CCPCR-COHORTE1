"""Contraseñas (scrypt), protección CSRF y límite de intentos de ingreso."""
import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict

from fastapi import HTTPException, Request


def hash_password(password: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=sal, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(sal).decode() + "$" + base64.b64encode(h).decode()


def verificar_password(password: str, guardado: str) -> bool:
    try:
        _, sal, h = guardado.split("$")
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(sal), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


def token_csrf(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


def validar_csrf(request: Request, recibido: str):
    esperado = request.session.get("csrf", "")
    if not esperado or not hmac.compare_digest(esperado, recibido or ""):
        raise HTTPException(status_code=400, detail="El formulario venció. Recargue la página e intente de nuevo.")


_intentos: dict[str, list[float]] = defaultdict(list)


def limitar(clave: str, maximo: int = 5, ventana: int = 900):
    """Máximo `maximo` intentos fallidos por `ventana` segundos (por IP y por usuario)."""
    ahora = time.time()
    _intentos[clave] = [t for t in _intentos[clave] if ahora - t < ventana]
    if len(_intentos[clave]) >= maximo:
        raise HTTPException(status_code=429, detail="Demasiados intentos. Espere 15 minutos e intente de nuevo.")


def fallo(clave: str):
    _intentos[clave].append(time.time())
