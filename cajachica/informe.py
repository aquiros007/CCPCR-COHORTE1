"""Informe consolidado de incumplimientos: todas las unidades de negocio, documento por documento."""
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .db import BaseDatos
from .reglas import REGLAS
from .reporte import AZUL, FMT_FECHA, FMT_MONTO, _pares, _tabla, _titulo

ACCIONES = {
    "DUPLICADO_EXACTO": "Excluir del reintegro. Solicitar explicación escrita al custodio.",
    "POSIBLE_DUPLICADO": "Pedir ambos comprobantes originales y confirmar que son compras distintas.",
    "PENDIENTE_YA_LIQUIDADO": "Retirar del arqueo y recalcular; investigar el faltante real.",
    "SIN_DATOS_INSTITUCION": "Excluir del reintegro. Solicitar al proveedor refacturar a nombre de la institución.",
    "RECEPTOR_INCORRECTO": "Excluir del reintegro. La factura está a nombre de un tercero.",
    "TIPO_DOCUMENTO": "Excluir del reintegro. Solicitar factura electrónica en lugar del tiquete.",
    "SIN_CLAVE": "Solicitar la clave numérica o el XML de la factura.",
    "CLAVE_INVALIDA": "Verificar la factura en el portal de Hacienda.",
    "CLAVE_ILEGIBLE": "Pedir al custodio corregir el formato de la clave y reenviar.",
    "INCONSISTENCIA_CLAVE": "Verificar la factura en el portal de Hacienda; posible alteración.",
    "EXCEDE_LIMITE": "Excluir del reintegro o tramitar por compras ordinarias.",
    "GASTO_PROHIBIDO": "Excluir del reintegro; el custodio debe reponer el monto.",
    "CONFLICTO_INTERES": "Excluir del reintegro y escalar a Auditoría Interna.",
    "FRACCIONAMIENTO": "Revisar si la compra debió tramitarse por proveeduría.",
    "DIFERENCIA_REINTEGRO": "Ajustar el monto solicitado al total de facturas válidas.",
    "EXCEDE_FONDO": "Revisar el fondo asignado y el origen del exceso.",
    "FALTANTE_ARQUEO": "Solicitar reposición inmediata al custodio y justificación escrita.",
    "SOBRANTE_ARQUEO": "Identificar el comprobante o ingreso no registrado.",
    "CAJA_NO_REGISTRADA": "Confirmar el código de caja o registrar la unidad en el catálogo.",
    "CAJA_INACTIVA": "Confirmar por qué una caja inactiva sigue operando.",
    "CUSTODIO_NO_AUTORIZADO": "Confirmar cambio de custodio y actualizar el catálogo.",
    "APROBADOR_NO_AUTORIZADO": "Obtener la aprobación de un aprobador autorizado.",
    "SIN_AUTORIZACION": "Obtener la aprobación antes de reintegrar.",
    "AUTOAPROBACION": "Obtener aprobación de la jefatura (segregación de funciones).",
    "CATEGORIA_NO_AUTORIZADA": "Reclasificar o justificar; si no procede, excluir.",
    "REQUIERE_JUSTIFICACION": "Solicitar justificación del fin institucional.",
    "FACTURA_VENCIDA": "Justificar la presentación tardía o excluir.",
    "FECHA_FUTURA": "Verificar la fecha; posible error o documento alterado.",
    "ERROR_CALCULO": "Verificar montos contra el comprobante original.",
    "VALE_VENCIDO": "Exigir la liquidación del vale o su devolución.",
    "PENDIENTE_VENCIDO": "Incluir en la próxima liquidación o justificar.",
}
ORDEN = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}


def generar_informe(ruta_db: Path, politica: dict, desde: date, hasta: date, destinos: list[Path],
                    incluir_bajas: bool = False) -> list[Path]:
    db = BaseDatos(ruta_db)
    catalogo = politica.get("_catalogo") or {}
    refs = politica.get("referencias_politica") or {}
    sevs = ("ALTA", "MEDIA", "BAJA") if incluir_bajas else ("ALTA", "MEDIA")
    marcas = ",".join("?" * len(sevs))
    rango = (desde.isoformat(), hasta.isoformat())

    liqs = db.consultar("SELECT * FROM liquidaciones WHERE fecha BETWEEN ? AND ?", rango)
    arqs = db.consultar("SELECT * FROM arqueos WHERE fecha BETWEEN ? AND ?", rango)
    hall_fact = db.consultar(f"""
        SELECT h.severidad, h.regla, h.detalle, f.id AS factura_id, f.caja, f.fila, f.fecha, f.proveedor,
               f.cedula_proveedor, f.consecutivo, f.clave, f.descripcion, f.total_crc, f.estado,
               l.numero AS liquidacion, l.custodio, l.fecha AS fecha_liq, a.nombre AS archivo
        FROM hallazgos h JOIN facturas f ON f.id = h.factura_id
        JOIN liquidaciones l ON l.id = h.liquidacion_id JOIN archivos a ON a.id = h.archivo_id
        WHERE l.fecha BETWEEN ? AND ? AND h.severidad IN ({marcas})""", rango + sevs)
    hall_gen = db.consultar(f"""
        SELECT h.severidad, h.regla, h.detalle, h.monto, h.caja, h.origen, l.numero AS liquidacion,
               COALESCE(l.custodio, q.custodio) AS custodio, COALESCE(l.fecha, q.fecha) AS fecha, a.nombre AS archivo
        FROM hallazgos h LEFT JOIN liquidaciones l ON l.id = h.liquidacion_id
        LEFT JOIN arqueos q ON q.id = h.arqueo_id JOIN archivos a ON a.id = h.archivo_id
        WHERE h.factura_id IS NULL AND COALESCE(l.fecha, q.fecha) BETWEEN ? AND ? AND h.severidad IN ({marcas})""",
                          rango + sevs)
    db.cerrar()

    unidad = lambda c: (catalogo.get(c) or {}).get("unidad", "")
    responsable = lambda c, alterno="": (catalogo.get(c) or {}).get("responsable") or alterno

    # ---- documentos: una fila por factura, con todos sus incumplimientos
    docs = {}
    for h in hall_fact:
        d = docs.setdefault(h["factura_id"], {**h, "hallazgos": []})
        d["hallazgos"].append(h)
    filas_docs = []
    for d in docs.values():
        hs = sorted(d["hallazgos"], key=lambda x: ORDEN[x["severidad"]])
        filas_docs.append([
            hs[0]["severidad"], d["caja"], unidad(d["caja"]), responsable(d["caja"], d["custodio"]), d["liquidacion"],
            d["archivo"], d["fila"], d["fecha"] and date.fromisoformat(d["fecha"]), d["proveedor"], d["cedula_proveedor"],
            d["consecutivo"], d["clave"], d["descripcion"], d["total_crc"], d["estado"],
            "\n".join(f"• [{x['severidad']}] {REGLAS.get(x['regla'], x['regla'])}: {x['detalle']}" for x in hs),
            "\n".join(sorted({refs[x["regla"]] for x in hs if refs.get(x["regla"])})),
            "\n".join(dict.fromkeys(ACCIONES[x["regla"]] for x in hs if x["regla"] in ACCIONES)),
        ])
    filas_docs.sort(key=lambda r: (ORDEN[r[0]], r[1], str(r[4]), r[6] or 0))

    filas_gen = sorted([[
        h["severidad"], h["caja"], unidad(h["caja"]), responsable(h["caja"], h["custodio"]),
        "Arqueo" if h["origen"] == "arqueo" else f"Liquidación {h['liquidacion']}", h["archivo"],
        h["fecha"] and date.fromisoformat(h["fecha"]), REGLAS.get(h["regla"], h["regla"]), h["detalle"], h["monto"],
        refs.get(h["regla"], ""), ACCIONES.get(h["regla"], ""),
    ] for h in hall_gen], key=lambda r: (ORDEN[r[0]], r[1]))

    # ---- resumen por unidad
    por_caja = defaultdict(lambda: {"liq": 0, "total": 0, "fact": 0, "rech": 0, "obs": 0, "m_rech": 0, "m_obs": 0,
                                    "alta": 0, "arqueo": None})
    for l in liqs:
        u = por_caja[l["caja"]]
        u["liq"] += 1; u["total"] += l["total_facturas"] or 0; u["fact"] += l["n_facturas"]
        u["rech"] += l["n_rechazadas"]; u["obs"] += l["n_observadas"]
    for d in docs.values():
        u = por_caja[d["caja"]]
        if d["estado"] == "RECHAZADA":
            u["m_rech"] += d["total_crc"] or 0
        elif d["estado"] == "OBSERVADA":
            u["m_obs"] += d["total_crc"] or 0
    for h in hall_fact + hall_gen:
        if h["severidad"] == "ALTA":
            por_caja[h["caja"]]["alta"] += 1
    for a in sorted(arqs, key=lambda a: a["fecha"]):
        por_caja[a["caja"]]["arqueo"] = a
    for c in catalogo:
        por_caja[c]
    filas_unidad = []
    for c, u in por_caja.items():
        if not u["liq"] and not u["arqueo"]:
            semaforo = "SIN ENTREGA"
        elif u["alta"]:
            semaforo = "ROJO"
        elif u["obs"]:
            semaforo = "AMARILLO"
        else:
            semaforo = "VERDE"
        a = u["arqueo"]
        filas_unidad.append([semaforo, c, unidad(c), responsable(c), (catalogo.get(c) or {}).get("fondo"), u["liq"],
                             u["total"], u["fact"], u["rech"], u["m_rech"], u["obs"], u["m_obs"], u["alta"],
                             a and date.fromisoformat(a["fecha"]), a and a["diferencia"]])
    orden_sem = {"ROJO": 0, "AMARILLO": 1, "SIN ENTREGA": 2, "VERDE": 3}
    filas_unidad.sort(key=lambda r: (orden_sem[r[0]], -r[12], r[1]))

    # ---- libro
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    _titulo(ws, "Informe de incumplimientos — Caja Chica",
            f"Período {desde:%d/%m/%Y} al {hasta:%d/%m/%Y} · Generado {datetime.now():%d/%m/%Y %H:%M}")
    n_cat = len(catalogo) or len(por_caja)
    entregaron = sum(1 for r in filas_unidad if r[0] != "SIN ENTREGA")
    total = sum(r[6] for r in filas_unidad)
    m_rech = sum(r[9] for r in filas_unidad)
    fila = _pares(ws, 4, [
        ("Unidades de negocio", n_cat),
        ("Unidades que entregaron", entregaron),
        ("Unidades sin entrega en el período", sum(1 for r in filas_unidad if r[0] == "SIN ENTREGA")),
        ("Unidades en ROJO (incumplimientos graves)", sum(1 for r in filas_unidad if r[0] == "ROJO")),
        ("Liquidaciones revisadas", len(liqs)),
        ("Arqueos revisados", len(arqs)),
        ("Gasto presentado", total, FMT_MONTO),
        ("Monto que NO debe reintegrarse (rechazado)", m_rech, FMT_MONTO),
        ("Monto pendiente de justificar (observado)", sum(r[11] for r in filas_unidad), FMT_MONTO),
        ("Documentos con incumplimientos", len(filas_docs)),
        ("   de severidad ALTA", sum(1 for r in filas_docs if r[0] == "ALTA")),
        ("Incumplimientos de liquidación o arqueo", len(filas_gen)),
    ])
    ws.cell(row=fila + 1, column=1, value="Incumplimientos más frecuentes").font = Font(bold=True, color=AZUL)
    conteo = defaultdict(lambda: [0, 0.0])
    for h in hall_fact:
        conteo[h["regla"]][0] += 1; conteo[h["regla"]][1] += h["total_crc"] or 0
    for h in hall_gen:
        conteo[h["regla"]][0] += 1; conteo[h["regla"]][1] += abs(h["monto"] or 0)
    for i, (regla, (n, m)) in enumerate(sorted(conteo.items(), key=lambda x: -x[1][0])[:15], fila + 2):
        ws.cell(row=i, column=1, value=REGLAS.get(regla, regla))
        ws.cell(row=i, column=2, value=f"{n} casos · ₡{m:,.0f}")

    ws = wb.create_sheet("Por unidad")
    _tabla(ws, 1, ["Semáforo", "Código", "Unidad de negocio", "Responsable", "Fondo", "Liquidaciones", "Gasto presentado",
                   "Facturas", "Rechazadas", "Monto rechazado", "Observadas", "Monto observado", "Hallazgos ALTA",
                   "Último arqueo", "Diferencia arqueo"], filas_unidad,
           [13, 11, 28, 24, 13, 8, 15, 8, 9, 15, 9, 15, 9, 12, 14], montos=(5, 7, 10, 12, 15), fechas=(14,))
    colores = {"ROJO": "F8D7DA", "AMARILLO": "FFF3CD", "VERDE": "D4EDDA", "SIN ENTREGA": "E2E3E5"}
    for r in range(2, len(filas_unidad) + 2):
        c = ws.cell(row=r, column=1)
        c.fill = PatternFill("solid", fgColor=colores[c.value]); c.font = Font(bold=True)

    ws = wb.create_sheet("Documentos incumplidos")
    _tabla(ws, 1, ["Severidad", "Código", "Unidad", "Responsable", "Liquidación", "Archivo", "Fila", "Fecha factura",
                   "Proveedor", "Cédula proveedor", "N° factura", "Clave numérica", "Descripción", "Monto", "Estado",
                   "Incumplimientos", "Norma de la política", "Acción requerida"], filas_docs,
           [10, 11, 22, 20, 12, 30, 6, 12, 26, 14, 22, 20, 30, 12, 12, 70, 22, 40],
           col_estado=1, montos=(14,), fechas=(8,))

    ws = wb.create_sheet("Liquidaciones y arqueos")
    _tabla(ws, 1, ["Severidad", "Código", "Unidad", "Responsable", "Documento", "Archivo", "Fecha", "Incumplimiento",
                   "Detalle", "Monto", "Norma de la política", "Acción requerida"], filas_gen,
           [10, 11, 22, 20, 18, 30, 12, 34, 70, 13, 22, 40], col_estado=1, montos=(10,), fechas=(7,))

    sin = [[r[1], r[2], r[3], (catalogo.get(r[1]) or {}).get("correo", ""), r[4]] for r in filas_unidad if r[0] == "SIN ENTREGA"]
    ws = wb.create_sheet("Sin entrega")
    _tabla(ws, 1, ["Código", "Unidad de negocio", "Responsable", "Correo", "Fondo"], sin, [11, 30, 26, 30, 14], montos=(5,))

    escritos = []
    for d in destinos:
        d.parent.mkdir(parents=True, exist_ok=True)
        wb.save(d)
        escritos.append(d)
    return escritos
