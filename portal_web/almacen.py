"""Dónde quedan los archivos que suben los proveedores.

Google Drive: dentro de 01_Facturas de "Caja Chica U", en <año>/<MM-Mes>/<cédula> <proveedor>/<n.º factura>/.
Credenciales, en este orden:
  1. OAuth de la cuenta dueña de la carpeta (GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN). Es lo que funciona con
     una cuenta personal de Gmail: las cuentas de servicio no tienen espacio propio en "Mi unidad".
  2. Cuenta de servicio (GOOGLE_SERVICE_ACCOUNT_JSON), solo si la carpeta está en una Unidad compartida.
Local: STORAGE_DIR con la misma estructura (útil en desarrollo o con un volumen de Railway).
"""
import io
import json
from pathlib import Path

from . import config


class AlmacenLocal:
    nombre = "local"

    def __init__(self, base: Path):
        self.base = base

    def guardar(self, carpeta: list[str], nombre: str, contenido: bytes, tipo: str) -> dict:
        destino = self.base.joinpath(*carpeta)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / nombre).write_bytes(contenido)
        return {"id": str((destino / nombre).relative_to(self.base)), "nombre": nombre, "carpeta": "/".join(carpeta)}

    def leer(self, ident: str) -> bytes:
        ruta = (self.base / ident).resolve()
        if self.base.resolve() not in ruta.parents:
            raise PermissionError("Ruta fuera del almacenamiento")
        return ruta.read_bytes()


class AlmacenDrive:
    nombre = "drive"
    CARPETA = "application/vnd.google-apps.folder"

    def __init__(self, raiz_id: str):
        from googleapiclient.discovery import build
        self.raiz = raiz_id
        self.servicio = build("drive", "v3", credentials=self._credenciales(), cache_discovery=False)
        self._cache: dict[tuple, str] = {}

    @staticmethod
    def _credenciales():
        alcance = ["https://www.googleapis.com/auth/drive"]
        if config.GOOGLE_OAUTH_REFRESH_TOKEN:
            from google.oauth2.credentials import Credentials
            return Credentials(None, refresh_token=config.GOOGLE_OAUTH_REFRESH_TOKEN,
                               client_id=config.GOOGLE_OAUTH_CLIENT_ID, client_secret=config.GOOGLE_OAUTH_CLIENT_SECRET,
                               token_uri="https://oauth2.googleapis.com/token", scopes=alcance)
        if config.GOOGLE_SERVICE_ACCOUNT_JSON:
            from google.oauth2 import service_account
            return service_account.Credentials.from_service_account_info(
                json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON), scopes=alcance)
        raise RuntimeError("Faltan credenciales de Google (GOOGLE_OAUTH_* o GOOGLE_SERVICE_ACCOUNT_JSON).")

    def _carpeta(self, padre: str, nombre: str) -> str:
        if (padre, nombre) in self._cache:
            return self._cache[(padre, nombre)]
        seguro = nombre.replace("\\", "\\\\").replace("'", "\\'")
        r = self.servicio.files().list(
            q=f"name = '{seguro}' and '{padre}' in parents and mimeType = '{self.CARPETA}' and trashed = false",
            fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        if r.get("files"):
            ident = r["files"][0]["id"]
        else:
            ident = self.servicio.files().create(body={"name": nombre, "mimeType": self.CARPETA, "parents": [padre]},
                                                 fields="id", supportsAllDrives=True).execute()["id"]
        self._cache[(padre, nombre)] = ident
        return ident

    def guardar(self, carpeta: list[str], nombre: str, contenido: bytes, tipo: str) -> dict:
        from googleapiclient.http import MediaIoBaseUpload
        padre = self.raiz
        for parte in carpeta:
            padre = self._carpeta(padre, parte)
        archivo = self.servicio.files().create(
            body={"name": nombre, "parents": [padre]},
            media_body=MediaIoBaseUpload(io.BytesIO(contenido), mimetype=tipo, resumable=False),
            fields="id", supportsAllDrives=True).execute()
        return {"id": archivo["id"], "nombre": nombre, "carpeta": "/".join(carpeta), "carpeta_id": padre}

    def leer(self, ident: str) -> bytes:
        return self.servicio.files().get_media(fileId=ident, supportsAllDrives=True).execute()


_almacen = None


def almacen():
    global _almacen
    if _almacen is None:
        _almacen = AlmacenDrive(config.DRIVE_FACTURAS_FOLDER_ID) if config.ALMACEN == "drive" \
            else AlmacenLocal(config.STORAGE_DIR)
    return _almacen
