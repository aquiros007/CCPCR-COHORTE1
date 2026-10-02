"""Configuración del portal web por variables de entorno (Railway → Variables)."""
import os
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _bool(nombre: str, defecto: bool = False) -> bool:
    return os.environ.get(nombre, str(defecto)).strip().lower() in ("1", "true", "si", "sí", "yes")


PRODUCCION = _bool("PRODUCCION", bool(os.environ.get("RAILWAY_ENVIRONMENT")))

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if PRODUCCION:
        sys.exit("Falta la variable SECRET_KEY (cadena aleatoria larga para firmar las sesiones).")
    SECRET_KEY = secrets.token_urlsafe(48)  # solo desarrollo: las sesiones se pierden al reiniciar

_db = os.environ.get("DATABASE_URL", f"sqlite:///{RAIZ / 'data' / 'portal.db'}")
DATABASE_URL = _db.replace("postgres://", "postgresql+psycopg://", 1).replace("postgresql://", "postgresql+psycopg://", 1)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
API_TOKEN = os.environ.get("API_TOKEN", "")

STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", str(RAIZ / "data" / "portal_archivos")))
DRIVE_FACTURAS_FOLDER_ID = os.environ.get("DRIVE_FACTURAS_FOLDER_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REFRESH_TOKEN = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")

# Almacenamiento: Google Drive solo si hay carpeta Y credenciales; si no, disco (o volumen de Railway)
_credenciales_google = bool(GOOGLE_OAUTH_REFRESH_TOKEN or GOOGLE_SERVICE_ACCOUNT_JSON)
ALMACEN = os.environ.get("ALMACEN", "drive" if DRIVE_FACTURAS_FOLDER_ID and _credenciales_google else "local")

MAX_PDF_MB = float(os.environ.get("MAX_PDF_MB", "5"))
MAX_XML_KB = float(os.environ.get("MAX_XML_KB", "500"))
NOMBRE_PORTAL = os.environ.get("NOMBRE_PORTAL", "Portal de Proveedores")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")   # enlace al dashboard de caja chica (solo lo ven administradores)
