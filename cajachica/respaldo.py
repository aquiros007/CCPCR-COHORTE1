"""Respaldo en Google Drive (carpeta "Caja Chica U").

Calcula qué archivos son nuevos o cambiaron desde el último respaldo y a qué subcarpeta de Drive van.
La subida la hace Claude con el conector de Google Drive (o, si se instala Google Drive para escritorio,
`copiar_a_carpeta_local` copia directo a la carpeta sincronizada sin pasar por el conector).

Subcarpetas:
  01_Facturas/<AAAA>/<MM-Mes>/<cédula> <proveedor>/<número de factura>/
                                 Factura_<n>.pdf, Factura_<n>.xml y Respuesta_Hacienda_<n>.xml
                                 (mes de la fecha de emisión; cada documento se respalda en cuanto llega)
  01_Facturas/Sin_identificar    PDF que todavía no se pudo asociar a ninguna factura
  02_Proveedores                 registro de proveedores (versionado) y formularios de registro
  03_Liquidaciones_y_Arqueos/<AAAA-MM>   archivos originales que entregan las personas encargadas
  04_Revisiones/<AAAA-MM>        informe de revisión de cada archivo
  05_Informes_Consolidados       informes de incumplimientos
  06_Bitacora_de_Revision        bitácora exportada del dashboard y del portal (CSV)
  07_Configuracion_y_Politicas   política, catálogo, plantillas e instructivos (versionados)
  08_Base_de_Datos               copia consistente de la base SQLite (versionada)
"""
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import RAIZ, RUTA_CATALOGO, RUTA_DB, RUTA_POLITICA, RUTA_REPORTES, ruta_repositorio

RUTA_CONF_DRIVE = RAIZ / "config" / "respaldo_drive.json"   # ids de carpetas de Drive (fuera de git)
RUTA_COPIAS = RUTA_REPORTES / "respaldo"

TIPOS = {
    ".pdf": "application/pdf", ".xml": "application/xml", ".csv": "text/csv", ".txt": "text/plain",
    ".yaml": "text/plain", ".md": "text/markdown", ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".odt": "application/vnd.oasis.opendocument.text", ".db": "application/x-sqlite3",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
CATEGORIAS_DE_DATOS = {"facturas", "proveedores", "liquidaciones", "revisiones", "informes", "base_de_datos", "catalogo"}


MESES = ["01-Enero", "02-Febrero", "03-Marzo", "04-Abril", "05-Mayo", "06-Junio", "07-Julio", "08-Agosto",
         "09-Septiembre", "10-Octubre", "11-Noviembre", "12-Diciembre"]
NOMBRE_DOC = {"pdf": "Factura_{n}.pdf", "factura": "Factura_{n}.xml", "respuesta": "Respuesta_Hacienda_{n}.xml"}


def cedula_con_guiones(c: str) -> str:
    c = "".join(ch for ch in str(c or "") if ch.isdigit())
    if len(c) == 10 and c[0] in "2345":
        return f"{c[0]}-{c[1:4]}-{c[4:]}"          # jurídica
    if len(c) == 9:
        return f"{c[0]}-{c[1:5]}-{c[5:]}"          # física
    return c or "sin-cedula"


def _limpio(texto: str) -> str:
    return "".join(ch for ch in (texto or "") if ch not in '/\\:*?"<>|').strip()[:60]


def carpeta_factura(comp: dict) -> str:
    """01_Facturas/2026/09-Septiembre/3-101-456789 Librería El Estudiante S.A./00100001010000001520"""
    from .util import fecha
    f = fecha(comp.get("fecha")) or fecha(comp.get("fecha_recepcion")) or datetime.now().date()
    proveedor = f"{cedula_con_guiones(comp.get('emisor_cedula'))} {_limpio(comp.get('emisor_nombre'))}".strip()
    return f"01_Facturas/{f.year}/{MESES[f.month - 1]}/{proveedor}/{comp.get('consecutivo') or comp['clave'][21:41]}"


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _mes(ruta: Path) -> str:
    """Las carpetas del repositorio ya están por mes (AAAA-MM); si no, el mes de modificación."""
    for parte in reversed(ruta.parts):
        if len(parte) == 7 and parte[4] == "-" and parte[:4].isdigit():
            return parte
    return datetime.fromtimestamp(ruta.stat().st_mtime).strftime("%Y-%m")


def _version(ruta: Path) -> str:
    """Nombre con fecha para archivos que cambian (el conector de Drive no reemplaza contenido)."""
    return f"{ruta.stem}_{datetime.fromtimestamp(ruta.stat().st_mtime):%Y-%m-%d_%H%M}{ruta.suffix}"


def copia_base_de_datos() -> Path | None:
    """Copia consistente de SQLite (API de respaldo), solo si cambió desde la última copia."""
    if not RUTA_DB.exists():
        return None
    RUTA_COPIAS.mkdir(parents=True, exist_ok=True)
    temporal = RUTA_COPIAS / "_cajachica_tmp.db"
    origen, destino = sqlite3.connect(RUTA_DB), sqlite3.connect(temporal)
    with destino:
        origen.backup(destino)
    origen.close()
    destino.close()
    previas = sorted(RUTA_COPIAS.glob("cajachica_*.db"))
    if previas and _hash(previas[-1]) == _hash(temporal):
        temporal.unlink()
        return previas[-1]
    final = RUTA_COPIAS / f"cajachica_{datetime.now():%Y-%m-%d_%H%M}.db"
    temporal.rename(final)
    return final


def fuentes(politica: dict, db=None) -> list[dict]:
    repo = ruta_repositorio(politica)
    prov = repo / "07_Proveedores"
    items = []

    def agregar(ruta: Path, categoria: str, carpeta: str, nombre: str | None = None):
        if ruta.is_file() and not ruta.name.startswith((".", "~$", "_")) and ruta.suffix.lower() in TIPOS:
            items.append({"ruta": ruta, "categoria": categoria, "carpeta": carpeta, "nombre": nombre or ruta.name})

    asociados = set()
    if db is not None:
        for comp in db.consultar("SELECT * FROM comprobantes"):
            carpeta = carpeta_factura(comp)
            n = comp.get("consecutivo") or comp["clave"][21:41]
            for tipo, ruta in json.loads(comp["archivos"] or "{}").items():
                ruta = Path(ruta)
                if ruta.exists() and tipo in NOMBRE_DOC:
                    agregar(ruta, "facturas", carpeta, NOMBRE_DOC[tipo].format(n=n))
                    asociados.add(ruta)
    for f in (prov / "01_PDF").glob("*.pdf"):
        if f not in asociados:
            agregar(f, "facturas", "01_Facturas/Sin_identificar")
    from .comprobantes import RUTA_PROVEEDORES
    agregar(RUTA_PROVEEDORES, "proveedores", "02_Proveedores", _version(RUTA_PROVEEDORES) if RUTA_PROVEEDORES.exists() else None)
    for f in (prov / "00_Registro" / "procesados").glob("*"):
        agregar(f, "proveedores", "02_Proveedores")
    for f in (repo / "02_Procesados").glob("*/*"):
        agregar(f, "liquidaciones", f"03_Liquidaciones_y_Arqueos/{_mes(f)}")
    for f in (repo / "03_Revisiones").glob("*/*"):
        agregar(f, "revisiones", f"04_Revisiones/{_mes(f)}")
    for f in (repo / "06_Informes").glob("*"):
        agregar(f, "informes", "05_Informes_Consolidados")
    for f in (RUTA_REPORTES / "bitacora").glob("*.csv"):
        agregar(f, "bitacora", "06_Bitacora_de_Revision")
    agregar(RUTA_POLITICA, "configuracion", "07_Configuracion_y_Politicas", _version(RUTA_POLITICA))
    if RUTA_CATALOGO.exists():
        agregar(RUTA_CATALOGO, "catalogo", "07_Configuracion_y_Politicas", _version(RUTA_CATALOGO))
    for f in (RAIZ / "politicas").glob("*"):
        agregar(f, "configuracion", "07_Configuracion_y_Politicas")
    for f in (repo / "00_Plantillas").glob("*"):
        agregar(f, "configuracion", "07_Configuracion_y_Politicas/Plantillas")
    return items


def pendientes(politica: dict, db) -> dict:
    """Lo que falta respaldar. Mientras el dashboard diga 'Datos de demostración', solo configuración y políticas."""
    demo = bool((politica.get("dashboard") or {}).get("aviso"))
    if not demo:
        copia = copia_base_de_datos()
        lista = fuentes(politica, db) + ([{"ruta": copia, "categoria": "base_de_datos", "carpeta": "08_Base_de_Datos",
                                        "nombre": copia.name}] if copia else [])
    else:
        lista = [x for x in fuentes(politica, db) if x["categoria"] not in CATEGORIAS_DE_DATOS]
    hechos = {(r["ruta"], r["hash"]) for r in db.consultar("SELECT ruta, hash FROM respaldos")}
    salida = []
    for x in lista:
        h = _hash(x["ruta"])
        if (str(x["ruta"]), h) in hechos:
            continue
        salida.append({"ruta": str(x["ruta"]), "hash": h, "carpeta": x["carpeta"], "nombre": x["nombre"],
                       "categoria": x["categoria"], "tipo": TIPOS[x["ruta"].suffix.lower()],
                       "kb": round(x["ruta"].stat().st_size / 1024, 1)})
    return {"modo": "solo configuración (datos de demostración)" if demo else "completo",
            "pendientes": salida, "carpetas_necesarias": sorted({x["carpeta"] for x in salida})}


def registrar(db, ruta: str, hash_: str, drive_id: str, carpeta: str, nombre: str):
    db.con.execute("INSERT OR REPLACE INTO respaldos (ruta, hash, drive_id, carpeta, nombre, fecha) VALUES (?,?,?,?,?,?)",
                   (ruta, hash_, drive_id, carpeta, nombre, datetime.now().isoformat(timespec="seconds")))
    db.commit()


def copiar_a_carpeta_local(politica: dict, db, destino_base: Path) -> list[str]:
    """Con Google Drive para escritorio: copia directo a la carpeta sincronizada (sin el conector)."""
    hechos = []
    for x in pendientes(politica, db)["pendientes"]:
        destino = destino_base / x["carpeta"] / x["nombre"]
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(x["ruta"], destino)
        registrar(db, x["ruta"], x["hash"], f"local:{destino}", x["carpeta"], x["nombre"])
        hechos.append(str(destino))
    return hechos


def carpetas_faltantes(carpetas: list[str], ids: dict) -> list[str]:
    """Rutas de carpeta que hay que crear en Drive, de la más alta a la más profunda (padre antes que hijo)."""
    faltan = set()
    for c in carpetas:
        partes = c.split("/")
        for i in range(1, len(partes) + 1):
            sub = "/".join(partes[:i])
            if sub not in ids:
                faltan.add(sub)
    return sorted(faltan, key=lambda x: (x.count("/"), x))


def cargar_ids() -> dict:
    return json.loads(RUTA_CONF_DRIVE.read_text(encoding="utf-8")) if RUTA_CONF_DRIVE.exists() else {}


def guardar_ids(ids: dict):
    RUTA_CONF_DRIVE.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")
