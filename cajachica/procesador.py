"""Flujo principal: leer entrada -> revisar -> registrar -> informe -> mover archivo."""
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from .config import RUTA_DB, carpetas
from .db import BaseDatos
from .lectura import ErrorLectura, leer_archivo
from .reglas import REGLAS, _h, revisar_arqueo, revisar_liquidacion
from .comprobantes import comprobantes_por_clave, procesar_comprobantes
from .reporte import informe_arqueos, informe_liquidaciones
from .verificacion import clasificar, documentos_pendientes, lista_arqueo, lista_liquidacion

EXTENSIONES = {".xlsx", ".xlsm", ".xls", ".csv"}


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _mover(origen: Path, carpeta: Path) -> Path:
    destino = carpeta / datetime.now().strftime("%Y-%m") / origen.name
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino = destino.with_name(f"{destino.stem}_{datetime.now():%H%M%S}{destino.suffix}")
    shutil.move(str(origen), destino)
    return destino


def _guardar_hallazgo(db, h, archivo_id, origen, caja, liquidacion_id=None, arqueo_id=None, factura_id=None):
    db.insertar("hallazgos", {
        "archivo_id": archivo_id, "origen": origen, "liquidacion_id": liquidacion_id, "arqueo_id": arqueo_id,
        "factura_id": factura_id, "factura_relacionada_id": h.get("factura_relacionada_id"), "caja": caja,
        "severidad": h["severidad"], "regla": h["regla"], "detalle": h["detalle"], "monto": h.get("monto"),
        "fecha_registro": datetime.now().isoformat(timespec="seconds"),
        "gravedad": h.get("gravedad", ""), "articulo": h.get("articulo", ""),
    })


def _guardar_verificacion(db, lista, archivo_id, caja, liquidacion_id=None, arqueo_id=None):
    for i, it in enumerate(lista, 1):
        db.insertar("verificaciones", {"archivo_id": archivo_id, "liquidacion_id": liquidacion_id, "arqueo_id": arqueo_id,
                                       "caja": caja, "orden": i, "grupo": it["grupo"], "control": it["control"],
                                       "articulo": it["articulo"], "estado": it["estado"], "detalle": it["detalle"]})


def _procesar_liquidaciones(db, datos, archivo_id, politica):
    resultados = []
    ahora = datetime.now().isoformat(timespec="seconds")
    for liq in datos:
        enc = liq["encabezado"]
        previa = db.liquidacion_existente(enc["caja"], enc["numero"])
        if previa:
            db.eliminar_liquidacion(previa["id"])
        res = revisar_liquidacion(liq, politica, db.facturas_historicas())
        if previa:
            res["hallazgos_generales"].append(_h(
                "BAJA", "LIQUIDACION_REEMPLAZADA",
                f"Ya existía la liquidación {enc['numero']} (procesada {previa['fecha_proceso'][:10]}); "
                "se reemplazó por esta versión."))
        clasificar(res["hallazgos_generales"] + [h for f in res["facturas"] for h in f["hallazgos"]],
                   enc["caja"], politica, db, archivo_id)
        res["verificacion"] = lista_liquidacion(res, politica)
        res["pendientes"] = documentos_pendientes(res["verificacion"])
        r = res["resumen"]
        liq_id = db.insertar("liquidaciones", {
            "archivo_id": archivo_id, "caja": enc["caja"], "custodio": enc["custodio"],
            "cedula_custodio": enc["cedula_custodio"], "numero": enc["numero"],
            "fecha": enc["fecha_liquidacion"] or datetime.now().date(), "monto_solicitado": enc["monto_solicitado"],
            "total_facturas": r["total"], "n_facturas": r["n_facturas"], "n_rechazadas": r["n_rechazadas"],
            "n_observadas": r["n_observadas"], "estado": r["estado"], "fecha_proceso": ahora,
            "tipo_tramite": enc.get("tipo_tramite"),
        })
        _guardar_verificacion(db, res["verificacion"], archivo_id, enc["caja"], liquidacion_id=liq_id)
        for h in res["hallazgos_generales"]:
            _guardar_hallazgo(db, h, archivo_id, "liquidacion", enc["caja"], liquidacion_id=liq_id)
        for f in res["facturas"]:
            fac_id = db.insertar("facturas", {
                "liquidacion_id": liq_id, "archivo_id": archivo_id, "caja": enc["caja"], "fila": f["fila"],
                "fecha": f["fecha"], "tipo_doc": f["tipo_doc"], "clave": f["clave"], "consecutivo": f["consecutivo"],
                "proveedor": f["proveedor"], "cedula_proveedor": f["cedula_proveedor"], "receptor": f["receptor"],
                "cedula_receptor": f["cedula_receptor"], "descripcion": f["descripcion"], "categoria": f["categoria"],
                "subtotal": f["subtotal"], "iva": f["iva"], "total": f["total"], "moneda": f["moneda"],
                "total_crc": f["total_crc"], "solicitado_por": f["solicitado_por"], "autorizado_por": f["autorizado_por"],
                "estado": f["estado"],
                "observaciones": " | ".join(f"[{h['severidad']}] {h['titulo']}" for h in f["hallazgos"]),
            })
            f["id"] = fac_id
            for h in f["hallazgos"]:
                _guardar_hallazgo(db, h, archivo_id, "factura", enc["caja"], liquidacion_id=liq_id, factura_id=fac_id)
        db.commit()  # la siguiente liquidación del mismo archivo ya ve a esta en el histórico
        resultados.append(res)
    return resultados


def _procesar_arqueos(db, datos, archivo_id, politica):
    resultados = []
    ahora = datetime.now().isoformat(timespec="seconds")
    for a in datos:
        res = revisar_arqueo(a, politica, db.facturas_historicas())
        clasificar(res["hallazgos"], a["caja"], politica, db, archivo_id)
        res["verificacion"] = lista_arqueo(res, politica)
        res["pendientes"] = documentos_pendientes(res["verificacion"])
        arq_id = db.insertar("arqueos", {
            "archivo_id": archivo_id, "caja": a["caja"], "custodio": a["custodio"],
            "fecha": a["fecha"] or datetime.now().date(), "realizado_por": a["realizado_por"], "fondo": res["fondo"],
            "efectivo": a["efectivo"], "pendientes_facturas": a["pendientes_facturas"], "vales": a["vales"],
            "diferencia": res["diferencia"], "estado": res["estado"], "fecha_proceso": ahora,
        })
        for p in a["detalle_pendientes"]:
            db.insertar("arqueo_pendientes", {"arqueo_id": arq_id, **p})
        for h in res["hallazgos"]:
            _guardar_hallazgo(db, h, archivo_id, "arqueo", a["caja"], arqueo_id=arq_id)
        _guardar_verificacion(db, res["verificacion"], archivo_id, a["caja"], arqueo_id=arq_id)
        resultados.append(res)
    return resultados


def procesar(politica: dict) -> dict:
    rutas = carpetas(politica)
    db = BaseDatos(RUTA_DB)
    bitacora = {"proveedores": procesar_comprobantes(politica, db), "procesados": [], "omitidos": [], "rechazados": []}
    politica = {**politica, "_comprobantes": comprobantes_por_clave(db)}
    # Liquidaciones primero: así el arqueo puede detectar pendientes que ya fueron reintegrados
    archivos = sorted((p for p in rutas["entrada"].iterdir()
                       if p.is_file() and p.suffix.lower() in EXTENSIONES and not p.name.startswith(("~$", "."))),
                      key=lambda p: ("arqueo" in p.name.lower(), p.stat().st_mtime, p.name))
    for ruta in archivos:
        hash_ = _hash(ruta)
        if db.archivo_procesado(hash_):
            bitacora["omitidos"].append({"archivo": ruta.name, "motivo": "Idéntico a un archivo ya procesado"})
            _mover(ruta, rutas["procesados"])
            continue
        try:
            tipo, datos = leer_archivo(ruta)
        except ErrorLectura as e:
            destino = _mover(ruta, rutas["rechazados"])
            destino.with_suffix(".LEAME.txt").write_text(
                f"El archivo '{ruta.name}' no se pudo procesar.\n\nMotivo: {e}\n\n"
                "Descargue la plantilla desde la carpeta 00_Plantillas, complétela y vuelva a cargarla en 01_Entrada.\n",
                encoding="utf-8")
            bitacora["rechazados"].append({"archivo": ruta.name, "motivo": str(e)})
            continue

        archivo_id = db.insertar("archivos", {"nombre": ruta.name, "hash": hash_, "tipo": tipo,
                                              "fecha_proceso": datetime.now().isoformat(timespec="seconds"),
                                              "estado": "procesado"})
        nombre_informe = f"Revision_{ruta.stem}_{datetime.now():%Y%m%d_%H%M}.xlsx"
        destino_informe = rutas["revisiones"] / datetime.now().strftime("%Y-%m") / nombre_informe
        if tipo == "liquidacion":
            resultados = _procesar_liquidaciones(db, datos, archivo_id, politica)
            informe_liquidaciones(resultados, ruta.name, destino_informe)
            resumen = [{
                "caja": r["encabezado"]["caja"], "liquidacion": r["encabezado"]["numero"],
                "custodio": r["encabezado"]["custodio"], **{k: v for k, v in r["resumen"].items()},
                "hallazgos": _conteo(r["hallazgos_generales"] + [h for f in r["facturas"] for h in f["hallazgos"]]),
            } for r in resultados]
        else:
            resultados = _procesar_arqueos(db, datos, archivo_id, politica)
            informe_arqueos(resultados, ruta.name, destino_informe)
            resumen = [{"caja": a["caja"], "fecha": str(a["fecha"]), "estado": a["estado"],
                        "diferencia": a["diferencia"], "hallazgos": _conteo(a["hallazgos"])} for a in resultados]
        db.actualizar("archivos", archivo_id, {"revision": str(destino_informe)})
        db.commit()
        _mover(ruta, rutas["procesados"])
        bitacora["procesados"].append({"archivo": ruta.name, "tipo": tipo, "informe": str(destino_informe),
                                       "resultado": resumen})
    db.cerrar()
    return bitacora


def _conteo(hallazgos):
    c = {"ALTA": 0, "MEDIA": 0, "BAJA": 0}
    for h in hallazgos:
        c[h["severidad"]] += 1
    return c


__all__ = ["procesar", "REGLAS"]
