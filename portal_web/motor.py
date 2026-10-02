"""El motor de revisión de caja chica (cajachica/) corriendo dentro del portal.

Sus datos viven en el volumen de Railway (CAJACHICA_DATA_DIR): base SQLite del motor, repositorio de carpetas,
revisiones e informes. El SQLite admite un solo escritor, así que todo lo que escribe en el motor pasa por LOCK.
"""
import json
import shutil
import threading
import traceback
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import delete, insert, select, update

from cajachica import config as cc
from cajachica.comprobantes import carpetas_proveedores, guardar_proveedores
from cajachica.dashboard import _datos
from cajachica.db import BaseDatos
from cajachica.lectura import ErrorLectura, leer_archivo

from . import config, db
from .almacen import almacen

LOCK = threading.Lock()
TIPOS = {".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".csv": "text/csv",
         ".xls": "application/vnd.ms-excel", ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12"}


def politica() -> dict:
    return cc.cargar_politica()


def rutas() -> dict:
    return cc.carpetas(politica())


def carpeta_entregas() -> Path:
    p = cc.DATOS / "entregas"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------ verificación previa

def cajas_del_archivo(ruta: Path) -> tuple[str, set]:
    tipo, datos = leer_archivo(ruta)
    cajas = {(d["encabezado"]["caja"] if tipo == "liquidacion" else d["caja"]).upper() for d in datos}
    return tipo, cajas


# ------------------------------------------------------------------ respaldo en Drive (si está configurado)

def respaldar(carpeta: list[str], ruta: Path, nombre: str | None = None):
    import os
    raiz = os.environ.get("DRIVE_RAIZ_FOLDER_ID", "")
    if config.ALMACEN != "drive" or not raiz or not ruta.exists():
        return
    try:
        from .almacen import AlmacenDrive
        AlmacenDrive(raiz).guardar(carpeta, nombre or ruta.name, ruta.read_bytes(),
                                   TIPOS.get(ruta.suffix.lower(), "application/octet-stream"))
    except Exception as e:  # el respaldo nunca detiene la revisión
        db.registrar("motor", "error_respaldo", f"{ruta.name}: {e}")


# ------------------------------------------------------------------ proveedores del portal → motor

def sincronizar_proveedores(motor_db: BaseDatos) -> int:
    """Registro de proveedores y facturas del portal hacia el cruce del motor (sin datos de prueba)."""
    provs = db.todos(select(db.proveedores).where(db.proveedores.c.es_prueba.isnot(True)))
    guardar_proveedores({p["cedula"]: {
        "cedula": p["cedula"], "razon_social": p["razon_social"], "nombre_comercial": p.get("nombre_comercial") or "",
        "correo": p["correo"], "telefono": p.get("telefono") or "", "estado": p["estado"],
        "fecha_registro": p["creado"].date().isoformat() if p.get("creado") else "", "observaciones": "Portal web"}
        for p in provs})
    hechos = {r["envio"] for r in motor_db.consultar("SELECT envio FROM portal_importados")}
    carpetas = carpetas_proveedores(politica())
    nuevos = 0
    envs = db.todos(select(db.envios).join(db.proveedores).where(db.proveedores.c.es_prueba.isnot(True)))
    for e in envs:
        clave = f"web-{e['id']}"
        if clave in hechos or not e.get("archivos"):
            continue
        n = e["consecutivo"] or e["clave"][21:41]
        destinos = {"pdf": carpetas["pdf"] / f"Factura_{n}.pdf", "factura": carpetas["xml"] / f"Factura_{n}.xml",
                    "respuesta": carpetas["respuesta"] / f"Respuesta_Hacienda_{n}.xml"}
        try:
            for tipo, destino in destinos.items():
                destino.write_bytes(almacen().leer(e["archivos"][tipo]["id"]))
        except Exception as ex:
            db.registrar("motor", "error_importar_factura", f"{e['id']}: {ex}")
            continue
        motor_db.insertar("portal_importados", {"envio": clave, "persona": e["emisor_cedula"], "clave": e["clave"],
                                                "importado": date.today().isoformat()})
        if e["estado"] == "RECIBIDO":
            db.ejecutar(update(db.envios).where(db.envios.c.id == e["id"]).values(
                estado="EN_REVISION", comentario="En revisión por la Universidad.", actualizado=db.ahora()))
        nuevos += 1
    motor_db.commit()
    return nuevos


# ------------------------------------------------------------------ dashboard

def publicar_tablero():
    pol = politica()
    m = BaseDatos(cc.RUTA_DB)
    try:
        datos = _datos(m, pol["_catalogo"])
    finally:
        m.cerrar()
    datos["aviso"] = (pol.get("dashboard") or {}).get("aviso", "")
    datos["institucion"] = pol["institucion"].get("nombre", "")
    datos = json.loads(json.dumps(datos, default=str))
    db.ejecutar(insert(db.tablero).values(recibido=db.ahora(), generado=datos.get("generado", ""), datos=datos))
    viejos = db.todos(select(db.tablero.c.id).order_by(db.tablero.c.id.desc()).offset(10))
    if viejos:
        db.ejecutar(delete(db.tablero).where(db.tablero.c.id.in_([v["id"] for v in viejos])))


# ------------------------------------------------------------------ procesamiento

def _procesar_todo() -> dict:
    """Cruza proveedores, procesa lo que haya en 01_Entrada y publica el dashboard. Requiere LOCK."""
    from cajachica.procesador import procesar
    pol = politica()
    cc.carpetas(pol)
    m = BaseDatos(cc.RUTA_DB)
    try:
        sincronizar_proveedores(m)
    finally:
        m.cerrar()
    bitacora = procesar(pol)
    publicar_tablero()
    return bitacora


def procesar_entrega(entrega_id: int):
    e = db.uno(select(db.entregas).where(db.entregas.c.id == entrega_id))
    original = carpeta_entregas() / f"{entrega_id}_{e['archivo']}"
    with LOCK:
        db.ejecutar(update(db.entregas).where(db.entregas.c.id == entrega_id).values(estado="PROCESANDO"))
        try:
            entrada = rutas()["entrada"] / f"{entrega_id}_{e['archivo']}"
            shutil.copy2(original, entrada)
            bitacora = _procesar_todo()
            item = next((x for x in bitacora["procesados"] if x["archivo"] == entrada.name), None)
            rechazo = next((x for x in bitacora["rechazados"] if x["archivo"] == entrada.name), None)
            omitido = next((x for x in bitacora["omitidos"] if x["archivo"] == entrada.name), None)
            if item:
                valores = dict(estado="PROCESADO", tipo=item["tipo"], resultado=json.loads(json.dumps(item["resultado"], default=str)),
                               revision=item["informe"], mensaje="")
                mes = datetime.now().strftime("%Y-%m")
                respaldar(["03_Liquidaciones_y_Arqueos", mes], original, e["archivo"])
                respaldar(["04_Revisiones", mes], Path(item["informe"]))
            elif omitido:
                valores = dict(estado="RECHAZADO", mensaje="Este mismo archivo ya se había entregado antes.")
            else:
                valores = dict(estado="RECHAZADO", mensaje=(rechazo or {}).get("motivo", "No se pudo leer el archivo."))
        except Exception as ex:
            valores = dict(estado="ERROR", mensaje=f"Error al procesar: {ex}")
            db.registrar("motor", "error_procesar", traceback.format_exc()[-1500:])
        db.ejecutar(update(db.entregas).where(db.entregas.c.id == entrega_id).values(procesado=db.ahora(), **valores))
        db.registrar("motor", "entrega_procesada", f"{entrega_id} {e['archivo']} → {valores['estado']}")


def reprocesar_proveedores():
    """Para cuando llegan facturas de proveedores sin que haya liquidaciones nuevas."""
    with LOCK:
        _procesar_todo()


# ------------------------------------------------------------------ informe, catálogo, demostración, reinicio

def informe(desde: date, hasta: date) -> Path:
    from cajachica.informe import generar_informe
    nombre = f"Informe_Incumplimientos_{desde:%Y%m%d}_{hasta:%Y%m%d}.xlsx"
    destino = cc.RUTA_REPORTES / nombre
    with LOCK:
        generar_informe(cc.RUTA_DB, politica(), desde, hasta, [destino])
    respaldar(["05_Informes_Consolidados"], destino)
    return destino


def guardar_catalogo(contenido: bytes, nombre: str) -> dict:
    sufijo = ".csv" if nombre.lower().endswith(".csv") else ".xlsx"
    destino = cc.RUTA_CATALOGO.with_suffix(sufijo)
    temporal = destino.with_name("_nuevo" + sufijo)
    cc.RUTA_CONFIG.mkdir(parents=True, exist_ok=True)
    temporal.write_bytes(contenido)
    catalogo = cc.cargar_catalogo(temporal)
    if not catalogo:
        temporal.unlink()
        raise ValueError("El archivo no tiene filas con «Código caja (FUC)». Use la plantilla del catálogo.")
    for viejo in (cc.RUTA_CATALOGO, cc.RUTA_CATALOGO.with_suffix(".csv")):
        if viejo.exists():
            viejo.unlink()
    temporal.rename(destino)
    respaldar(["07_Configuracion_y_Politicas"], destino, f"Catalogo_Cajas_{datetime.now():%Y-%m-%d_%H%M}{sufijo}")
    return catalogo


def guardar_politica(contenido: bytes) -> dict:
    import yaml
    datos = yaml.safe_load(contenido.decode("utf-8"))
    for clave in ("institucion", "limites", "comprobantes"):
        if not isinstance(datos, dict) or clave not in datos:
            raise ValueError(f"La política no tiene la sección «{clave}». Parta de config/politica.ejemplo.yaml.")
    cc.RUTA_CONFIG.mkdir(parents=True, exist_ok=True)
    cc.RUTA_POLITICA.write_bytes(contenido)
    respaldar(["07_Configuracion_y_Politicas"], cc.RUTA_POLITICA, f"politica_{datetime.now():%Y-%m-%d_%H%M}.yaml")
    return datos


def cargar_demostracion():
    from cajachica.plantillas import CATALOGO_DEMO, crear_catalogo, crear_demo
    with LOCK:
        if not cc.RUTA_CATALOGO.exists():
            crear_catalogo(cc.RUTA_CATALOGO, CATALOGO_DEMO)
        crear_demo(rutas()["entrada"], politica())
        _procesar_todo()


def reiniciar_datos():
    """Borra los datos del motor (no las cuentas ni la política) y lo que el dashboard mostraba."""
    with LOCK:
        for p in (cc.DATOS / "data", cc.RUTA_REPORTES, cc.ruta_repositorio(politica()), carpeta_entregas()):
            shutil.rmtree(p, ignore_errors=True)
        for f in (cc.RUTA_CATALOGO, cc.RUTA_CATALOGO.with_suffix(".csv"), cc.RUTA_CONFIG / "Proveedores.xlsx"):
            if f.exists():
                f.unlink()
        for t in (db.tablero, db.validaciones, db.vigencias, db.entregas):
            db.ejecutar(delete(t))


def plantillas() -> dict:
    from cajachica.config import RUTA_CATALOGO
    from cajachica.plantillas import crear_catalogo, crear_plantillas
    carpeta = rutas()["plantillas"]
    archivos = {p.name: p for p in crear_plantillas(carpeta, politica())}
    cat = carpeta / "Plantilla_Catalogo_Cajas.xlsx"
    crear_catalogo(cat)
    archivos[cat.name] = cat
    return archivos
