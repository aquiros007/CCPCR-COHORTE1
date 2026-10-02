"""Lista de verificación del reglamento (CUMPLE / NO CUMPLE / NO SE PUEDE VERIFICAR / NO APLICA) y gravedad sugerida."""
from datetime import datetime, timedelta

from .config import info_caja
from .reglas import utes_requeridas

CUMPLE, NO_CUMPLE, NO_VERIFICABLE, NO_APLICA = "CUMPLE", "NO CUMPLE", "NO SE PUEDE VERIFICAR", "NO APLICA"
NIVELES = ["Leve", "Grave", "Muy grave"]
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
    "SIN_IFE": "Solicitar el código IFE de Sigesa de la factura.",
    "REQUIERE_AVAL_UTE": "Solicitar el oficio de aval de la UTE o la justificación de que no aplica.",
    "RETENCION_RENTA": "Verificar y aplicar la retención del 2 % de renta.",
    "GASTO_EXTRANJERO_INCOMPLETO": "Completar los datos mínimos del comprobante extranjero (art. 10).",
    "SIN_DECISION_INICIAL": "Solicitar la decisión inicial firmada por el titular subordinado.",
    "SIN_ESTADO_CUENTA": "Solicitar el estado de cuenta de la tarjeta institucional.",
    "SIN_DEVOLUCION": "Solicitar el comprobante de devolución de efectivo.",
    "PLAZO_REINTEGRO": "Registrar el atraso y recordar el plazo del 5.º día hábil.",
    "PLAZO_LIQUIDACION_FINAL": "Registrar el incumplimiento del calendario de cierre.",
    "MOVIMIENTO_NO_CONCILIADO": "Conciliar los movimientos bancarios contra las facturas y justificar las diferencias.",
    "FACTURA_RECHAZADA_HACIENDA": "Excluir del reintegro y solicitar al proveedor una factura aceptada.",
    "XML_NO_COINCIDE": "Corregir la liquidación con los datos del XML o verificar una posible alteración.",
    "SIN_ARQUEO_RECIENTE": "Programar un arqueo sin previo aviso.",
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
AVISO_ART_23 = ("Este informe es un apoyo a la revisión. La valoración final de las faltas corresponde a los "
                "órganos competentes (art. 23 del Reglamento de Cajas Chicas).")


# ------------------------------------------------------------------ gravedad

def gravedad_base(regla: str, politica: dict) -> str:
    g = politica.get("gravedad") or {}
    if regla in (g.get("muy_grave") or []):
        return "Muy grave"
    if regla in (g.get("grave") or []):
        return "Grave"
    if regla in (g.get("leve") or []):
        return "Leve"
    return ""


def clasificar(hallazgos: list[dict], caja: str, politica: dict, db, archivo_id: int) -> None:
    """Agrega 'gravedad' (sugerida, con reincidencia en 3 meses) y 'articulo' a cada hallazgo."""
    refs = politica.get("referencias_politica") or {}
    dias = int((politica.get("gravedad") or {}).get("reincidencia_dias", 90))
    desde = (datetime.now() - timedelta(days=dias)).isoformat()
    previos = {r["gravedad"]: r["n"] for r in db.consultar(
        "SELECT gravedad, COUNT(*) n FROM hallazgos WHERE caja=? AND fecha_registro>=? AND archivo_id<>? "
        "AND gravedad IS NOT NULL AND gravedad<>'' GROUP BY gravedad", (caja, desde, archivo_id))}
    for h in hallazgos:
        h["articulo"] = refs.get(h["regla"], "")
        base = gravedad_base(h["regla"], politica)
        if not base:
            h["gravedad"] = ""
            continue
        previo = next((k for k in previos if k.startswith(base)), None)
        if previo and base != "Muy grave":
            siguiente = NIVELES[NIVELES.index(base) + 1]
            h["gravedad"] = f"{siguiente} (reincidencia de faltas {base.lower()}s en {dias} días)"
        else:
            h["gravedad"] = base


# ------------------------------------------------------------------ lista de verificación de una liquidación

def _filas(res: dict, reglas: set) -> list[str]:
    return [f"fila {f['fila']}" for f in res["facturas"] if any(h["regla"] in reglas for h in f["hallazgos"])]


def _general(res: dict, reglas: set) -> list[dict]:
    return [h for h in res["hallazgos_generales"] if h["regla"] in reglas]


def _item(grupo, control, articulo, estado, detalle=""):
    return {"grupo": grupo, "control": control, "articulo": articulo, "estado": estado, "detalle": detalle}


def _por_reglas(grupo, control, articulo, res, reglas, ok="", aplica=True, na=""):
    if not aplica:
        return _item(grupo, control, articulo, NO_APLICA, na)
    filas = _filas(res, reglas)
    generales = _general(res, reglas)
    if filas or generales:
        partes = []
        if filas:
            partes.append(", ".join(filas))
        partes += [g["detalle"] for g in generales]
        return _item(grupo, control, articulo, NO_CUMPLE, " · ".join(partes))
    return _item(grupo, control, articulo, CUMPLE, ok)


def lista_liquidacion(res: dict, politica: dict) -> list[dict]:
    enc, facturas = res["encabezado"], res["facturas"]
    tipo = enc.get("tipo_tramite") or "Reintegro mensual"
    final = tipo == "Liquidación final"
    n = len(facturas)
    L = []
    D, F, N, P, C, U = ("Documentos del trámite", "Requisitos de cada factura", "Naturaleza de la compra",
                        "Plazos", "Controles", "Apertura y responsables")

    # --- Documentos del trámite (art. 6 c)
    L.append(_por_reglas(D, "Decisión inicial firmada por el titular subordinado", "Art. 6 c", res,
                         {"SIN_DECISION_INICIAL"}, f"Decisión {enc.get('decision_inicial')}."))
    L.append(_por_reglas(D, "Facturas o comprobantes autorizados", "Art. 6 c", res,
                         {"TIPO_DOCUMENTO", "SIN_CLAVE", "CLAVE_INVALIDA"}, f"{n} comprobantes."))
    con_ute = [f for f in facturas if utes_requeridas(f, politica)]
    L.append(_por_reglas(D, "Avales de UTE cuando se requieren", "Arts. 7, 7 bis, 7 ter", res, {"REQUIERE_AVAL_UTE"},
                         f"{len(con_ute)} compras con aval indicado.", aplica=bool(con_ute),
                         na="Ninguna compra coincide con las restricciones de las UTE."))
    ret = politica.get("retencion_renta") or {}
    con_ret = [f for f in facturas if f.get("retencion") is not None]
    if _filas(res, {"RETENCION_RENTA"}):
        L.append(_item(D, "Retención del 2 % de renta", "Art. 6 c", NO_CUMPLE, ", ".join(_filas(res, {"RETENCION_RENTA"}))))
    elif con_ret:
        L.append(_item(D, "Retención del 2 % de renta", "Art. 6 c", CUMPLE, f"{len(con_ret)} facturas con retención correcta."))
    elif ret.get("monto_minimo") is not None:
        L.append(_item(D, "Retención del 2 % de renta", "Art. 6 c", NO_APLICA, "Ninguna compra alcanza el monto que obliga a retener."))
    else:
        L.append(_item(D, "Retención del 2 % de renta", "Art. 6 c", NO_VERIFICABLE,
                       "No se registró retención y falta definir (PGF) desde qué monto aplica."))
    L.append(_por_reglas(D, "Devolución de efectivo", "Art. 6 c", res, {"SIN_DEVOLUCION"},
                         f"Devolución registrada: ₡{(enc.get('devolucion') or 0):,.0f}.", aplica=final,
                         na="Solo en liquidaciones finales."))
    L.append(_por_reglas(D, "Estado de cuenta de la tarjeta institucional", "Art. 6 c", res, {"SIN_ESTADO_CUENTA"},
                         "Adjunto.", aplica=final, na="Solo en liquidaciones finales."))

    # --- Requisitos de cada factura (art. 6 d)
    L.append(_por_reglas(F, "A nombre de la Universidad Nacional", "Art. 6 d", res,
                         {"SIN_DATOS_INSTITUCION", "RECEPTOR_INCORRECTO"}))
    sin_emisor = [f"fila {f['fila']}" for f in facturas if not f["proveedor"] or (not f["cedula_proveedor"] and not f.get("extranjero"))]
    L.append(_item(F, "Nombre o razón social y cédula del emisor", "Art. 6 d", NO_CUMPLE if sin_emisor else CUMPLE,
                   ", ".join(sin_emisor)))
    sin_num = [f"fila {f['fila']}" for f in facturas if not f["consecutivo"]]
    L.append(_item(F, "Numeración consecutiva", "Art. 6 d", NO_CUMPLE if sin_num else CUMPLE, ", ".join(sin_num)))
    L.append(_por_reglas(F, "Fecha de emisión válida", "Art. 6 d", res, {"FECHA_FUTURA"}) if all(f["fecha"] for f in facturas)
             else _item(F, "Fecha de emisión válida", "Art. 6 d", NO_CUMPLE,
                        ", ".join(f"fila {f['fila']}" for f in facturas if not f["fecha"])))
    sin_desc = [f"fila {f['fila']}" for f in facturas if not f["descripcion"] or f["total"] is None]
    L.append(_item(F, "Descripción y valor del bien o servicio", "Art. 6 d", NO_CUMPLE if sin_desc else CUMPLE, ", ".join(sin_desc)))
    sin_iva = [f"fila {f['fila']}" for f in facturas if f["iva"] is None]
    if sin_iva or _filas(res, {"TASA_IVA"}):
        L.append(_item(F, "Indica el IVA cobrado", "Art. 6 d", NO_CUMPLE, ", ".join(sin_iva + _filas(res, {"TASA_IVA"}))))
    else:
        L.append(_item(F, "Indica el IVA cobrado", "Art. 6 d", CUMPLE))
    L.append(_por_reglas(F, "Aritmética correcta (subtotal + IVA = total)", "Art. 6 d", res, {"ERROR_CALCULO"}))

    nacionales = [f for f in facturas if not f.get("extranjero")]
    con_xml = [f for f in nacionales if f.get("respaldo_xml")]
    rech = _filas(res, {"FACTURA_RECHAZADA_HACIENDA", "XML_NO_COINCIDE"})
    if rech:
        L.append(_item(F, "Factura electrónica validada por Hacienda", "Art. 6 d", NO_CUMPLE, ", ".join(rech)))
    elif nacionales and len(con_xml) == len(nacionales):
        L.append(_item(F, "Factura electrónica validada por Hacienda", "Art. 6 d", CUMPLE,
                       "Todas cruzadas contra XML y respuesta de Hacienda."))
    elif nacionales:
        faltan = [f"fila {f['fila']}" for f in nacionales if not f.get("respaldo_xml")]
        L.append(_item(F, "Factura electrónica validada por Hacienda", "Art. 6 d", NO_VERIFICABLE,
                       f"Sin XML ni respuesta de Hacienda: {', '.join(faltan)}. Solicítelos al proveedor."))
    else:
        L.append(_item(F, "Factura electrónica validada por Hacienda", "Art. 6 d", NO_APLICA, "Solo gastos en el extranjero."))
    if not any(f.get("tiene_col_ife") for f in facturas):
        L.append(_item(F, "Código IFE (Sigesa)", "Art. 6 d", NO_VERIFICABLE, "El archivo no trae la columna Código IFE."))
    else:
        L.append(_por_reglas(F, "Código IFE (Sigesa)", "Art. 6 d", res, {"SIN_IFE"}))
    revisados = [f for f in nacionales if f.get("respaldo_xml") == "LISTO PARA APROBACIÓN"]
    L.append(_item(F, "Sin alteraciones físicas", "Art. 6 d",
                   CUMPLE if nacionales and len(revisados) == len(nacionales) else NO_VERIFICABLE,
                   "PDF cruzado contra el XML en todas las facturas." if nacionales and len(revisados) == len(nacionales)
                   else "Requiere revisar el PDF o la foto de cada factura (o recibir PDF + XML del proveedor)."))
    L.append(_por_reglas(F, "Fechas dentro del período", "Arts. 6 d y 8", res, {"FUERA_DE_PERIODO", "FACTURA_VENCIDA"}))
    L.append(_por_reglas(F, "Sin facturas duplicadas", "Art. 6 d", res, {"DUPLICADO_EXACTO", "POSIBLE_DUPLICADO"}))
    ext = [f for f in facturas if f.get("extranjero")]
    L.append(_por_reglas(F, "Gastos en el extranjero con datos mínimos", "Art. 10", res, {"GASTO_EXTRANJERO_INCOMPLETO"},
                         f"{len(ext)} gastos en el extranjero.", aplica=bool(ext), na="No hay gastos en el extranjero."))

    # --- Naturaleza de la compra (arts. 3, 6 a)
    L.append(_por_reglas(N, "Compra permitida por caja chica (sin inmuebles ni equipo de transporte)", "Arts. 3 b-d y 6 a",
                         res, {"GASTO_PROHIBIDO", "CATEGORIA_NO_AUTORIZADA"}))
    L.append(_por_reglas(N, "No supera el monto máximo ni hay fragmentación", "Arts. 3 y 6 a", res,
                         {"EXCEDE_LIMITE", "FRACCIONAMIENTO"}))
    just = _filas(res, {"REQUIERE_JUSTIFICACION"})
    L.append(_item(N, "Gasto menor, indispensable e impostergable", "Art. 3", NO_VERIFICABLE,
                   ("Requieren justificación: " + ", ".join(just) + ". ") if just else
                   "Requiere criterio del revisor sobre cada descripción."))

    # --- Plazos
    L.append(_por_reglas(P, "Reintegro presentado a más tardar el 5.º día hábil del mes siguiente", "Arts. 8, 14, 15, 17, 18",
                         res, {"PLAZO_REINTEGRO"}, aplica=tipo == "Reintegro mensual", na=f"Trámite: {tipo}.")
             if enc.get("fecha_liquidacion") or tipo != "Reintegro mensual" else
             _item(P, "Reintegro presentado a más tardar el 5.º día hábil del mes siguiente", "Arts. 8, 14, 15, 17, 18",
                   NO_VERIFICABLE, "Falta la fecha de presentación."))
    limite_final = (politica.get("plazos") or {}).get("fecha_limite_liquidacion_final")
    if not final:
        L.append(_item(P, "Liquidación final dentro del calendario de cierre", "Arts. 8, 14, 15, 17, 18", NO_APLICA, f"Trámite: {tipo}."))
    elif not limite_final:
        L.append(_item(P, "Liquidación final dentro del calendario de cierre", "Arts. 8, 14, 15, 17, 18", NO_VERIFICABLE,
                       "Falta la fecha del calendario de cierre del PGF en la configuración."))
    else:
        L.append(_por_reglas(P, "Liquidación final dentro del calendario de cierre", "Arts. 8, 14, 15, 17, 18", res,
                             {"PLAZO_LIQUIDACION_FINAL"}))

    # --- Controles
    if res.get("movimientos") is None:
        L.append(_item(C, "Movimientos bancarios coinciden con las compras", "Art. 11 h", NO_VERIFICABLE,
                       "No se adjuntó la hoja de movimientos bancarios."))
    else:
        L.append(_por_reglas(C, "Movimientos bancarios coinciden con las compras", "Art. 11 h", res, {"MOVIMIENTO_NO_CONCILIADO"}))
    L.append(_por_reglas(C, "Monto solicitado concuerda con las facturas y no excede el fondo", "Art. 12 c", res,
                         {"DIFERENCIA_REINTEGRO", "EXCEDE_FONDO"}))
    L.append(_por_reglas(C, "Aprobación del gasto por persona autorizada", "Art. 6 c", res,
                         {"SIN_AUTORIZACION", "APROBADOR_NO_AUTORIZADO", "AUTOAPROBACION"}))

    # --- Apertura y responsables (arts. 4, 5, 13 b)
    L.append(_por_reglas(U, "Caja registrada, activa y entregada por la persona encargada", "Arts. 4 y 5", res,
                         {"CAJA_NO_REGISTRADA", "CAJA_INACTIVA", "CUSTODIO_NO_AUTORIZADO"}))
    L.append(item_tope_fondo(enc["caja"], politica))
    return L


def item_tope_fondo(caja: str, politica: dict) -> dict:
    ap = politica.get("apertura") or {}
    info = info_caja(politica, caja) or {}
    ctrl, art, grupo = "Fondo no supera el 10 % del monto de licitación reducida", "Arts. 4, 5 y 13 b", "Apertura y responsables"
    if not ap.get("monto_licitacion_reducida"):
        return _item(grupo, ctrl, art, NO_VERIFICABLE, "Falta el monto vigente de licitación reducida (PGF) en la configuración.")
    if not info.get("fondo"):
        return _item(grupo, ctrl, art, NO_VERIFICABLE, "La caja no tiene fondo registrado en el catálogo.")
    tope = float(ap["monto_licitacion_reducida"]) * float(ap.get("porcentaje_tope_fondo", 10)) / 100
    return _item(grupo, ctrl, art, CUMPLE if info["fondo"] <= tope else NO_CUMPLE,
                 f"Fondo ₡{info['fondo']:,.0f}; tope ₡{tope:,.0f}.")


# ------------------------------------------------------------------ lista de verificación de un arqueo

def lista_arqueo(res: dict, politica: dict) -> list[dict]:
    reglas = {h["regla"] for h in res["hallazgos"]}
    det = {h["regla"]: h["detalle"] for h in res["hallazgos"]}
    G = "Arqueo"

    def por(control, art, rs, ok="", aplica=True, na=""):
        if not aplica:
            return _item(G, control, art, NO_APLICA, na)
        hit = [det[r] for r in rs if r in reglas]
        return _item(G, control, art, NO_CUMPLE if hit else CUMPLE, " · ".join(hit) or ok)

    tipo = (res.get("tipo_arqueo") or "").lower()
    L = [
        por("Concordancia entre monto asignado, efectivo, vales y justificantes", "Art. 12 c",
            ["FALTANTE_ARQUEO", "SOBRANTE_ARQUEO", "PENDIENTE_YA_LIQUIDADO"], "Cuadra con el fondo."),
        por("Fondo declarado igual al asignado", "Art. 12 c", ["FONDO_DIFERENTE"]),
        por("Realizado por la persona responsable o el PGF", "Arts. 14 y 17", ["ARQUEO_NO_INDEPENDIENTE"], res.get("realizado_por", "")),
        _item(G, "Arqueo sin previo aviso", "Arts. 14 y 17",
              CUMPLE if "sin previo" in tipo else NO_CUMPLE if "program" in tipo else NO_VERIFICABLE,
              res.get("tipo_arqueo") or "El archivo no indica si fue sin previo aviso."),
        _item(G, "Comprobante del arqueo enviado al PGF", "Arts. 14 y 17", NO_VERIFICABLE, "Confirmar el envío al PGF."),
        por("Vales liquidados en 5 días hábiles", "Arts. 8, 14, 15, 17, 18", ["VALE_VENCIDO"],
            aplica=res["vales"] > 0 or any("VALE" in (p.get("tipo") or "").upper() for p in res["detalle_pendientes"]),
            na="No hay vales pendientes."),
        por("Faltante cubierto el mismo día / sobrante reintegrado al día hábil siguiente", "Art. 17",
            ["FALTANTE_ARQUEO", "SOBRANTE_ARQUEO"], aplica=abs(res["diferencia"]) > politica["limites"].get("tolerancia_arqueo", 0),
            na="Sin faltante ni sobrante."),
        por("Caja registrada y persona encargada autorizada", "Arts. 4 y 5",
            ["CAJA_NO_REGISTRADA", "CAJA_INACTIVA", "CUSTODIO_NO_AUTORIZADO"]),
    ]
    return L


def documentos_pendientes(lista: list[dict]) -> list[str]:
    """Lo que hay que pedir para poder cerrar la revisión."""
    pendientes = []
    for it in lista:
        if it["estado"] == NO_VERIFICABLE:
            pendientes.append(f"{it['control']}: {it['detalle']}")
        elif it["estado"] == NO_CUMPLE and it["control"].startswith(("Decisión inicial", "Devolución", "Estado de cuenta", "Avales")):
            pendientes.append(f"{it['control']}: {it['detalle']}")
    return pendientes
