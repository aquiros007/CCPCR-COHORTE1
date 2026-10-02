"""Reglas de auditoría de caja chica.

Severidades:
  ALTA  -> la factura no debe reintegrarse hasta aclararse (estado RECHAZADA)
  MEDIA -> requiere justificación o corrección (estado OBSERVADA)
  BAJA  -> señal de riesgo informativa (no cambia el estado)
"""
from collections import defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher

from .config import fondo_de_caja, info_caja
from .util import TIPOS_DOCUMENTO, clave_ilegible, descomponer_clave, fecha, normalizar, solo_digitos

REGLAS = {
    "COMPROBANTE_INCOMPLETO": "Faltan datos obligatorios del comprobante",
    "SIN_DATOS_INSTITUCION": "La factura no trae los datos de la institución",
    "RECEPTOR_INCORRECTO": "La factura está a nombre de otra persona o entidad",
    "NOMBRE_RECEPTOR_DIFERENTE": "El nombre del receptor no coincide exactamente",
    "SIN_CLAVE": "Sin clave numérica de factura electrónica",
    "CLAVE_ILEGIBLE": "Clave dañada por formato numérico de Excel",
    "CLAVE_INVALIDA": "Clave numérica con estructura inválida",
    "INCONSISTENCIA_CLAVE": "Los datos de la clave no coinciden con lo digitado",
    "TIPO_DOCUMENTO": "Tipo de comprobante no aceptado",
    "EXCEDE_LIMITE": "Supera el monto máximo por gasto de caja chica",
    "ERROR_CALCULO": "Subtotal + IVA no coincide con el total",
    "TASA_IVA": "Tasa de IVA inusual",
    "FECHA_FUTURA": "Factura con fecha posterior a la liquidación",
    "FACTURA_VENCIDA": "Factura más antigua que lo permitido",
    "FUERA_DE_PERIODO": "Factura fuera del período liquidado",
    "FIN_DE_SEMANA": "Gasto en fin de semana",
    "CATEGORIA_NO_AUTORIZADA": "Categoría no autorizada para caja chica",
    "GASTO_PROHIBIDO": "Concepto prohibido por la política",
    "REQUIERE_JUSTIFICACION": "Concepto sensible: requiere justificación",
    "MONTO_REDONDO": "Monto redondo exacto",
    "SIN_AUTORIZACION": "Gasto sin aprobador",
    "AUTOAPROBACION": "El gasto lo aprueba la misma persona que lo solicita",
    "CONFLICTO_INTERES": "El proveedor es el custodio o el solicitante",
    "MONTO_INVALIDO": "Monto cero o negativo",
    "DUPLICADO_EXACTO": "Factura duplicada",
    "POSIBLE_DUPLICADO": "Posible factura duplicada",
    "COMPRA_REPETIDA": "Compra repetida al mismo proveedor por el mismo monto",
    "FRACCIONAMIENTO": "Posible fraccionamiento de compras",
    "DIFERENCIA_REINTEGRO": "El monto solicitado no cuadra con las facturas",
    "EXCEDE_FONDO": "La liquidación supera el fondo asignado",
    "LIQUIDACION_ANTICIPADA": "Liquidación con bajo porcentaje de uso del fondo",
    "LIQUIDACION_REEMPLAZADA": "Se recibió una nueva versión de la liquidación",
    "SIN_CUSTODIO": "Liquidación sin custodio identificado",
    "FALTANTE_ARQUEO": "Faltante de efectivo en el arqueo",
    "SOBRANTE_ARQUEO": "Sobrante de efectivo en el arqueo",
    "FONDO_DIFERENTE": "El fondo declarado no coincide con el asignado",
    "ARQUEO_NO_INDEPENDIENTE": "El arqueo lo realizó el mismo custodio",
    "VALE_VENCIDO": "Vale o adelanto pendiente fuera de plazo",
    "PENDIENTE_VENCIDO": "Factura pendiente de liquidar fuera de plazo",
    "PENDIENTE_YA_LIQUIDADO": "Comprobante del arqueo ya fue reintegrado en una liquidación",
    "CAJA_NO_REGISTRADA": "La caja no existe en el catálogo de unidades",
    "CAJA_INACTIVA": "La caja está marcada como inactiva",
    "CUSTODIO_NO_AUTORIZADO": "Quien entrega no es el responsable registrado de la caja",
    "APROBADOR_NO_AUTORIZADO": "El gasto lo aprobó alguien que no está autorizado para esa caja",
}


def verificar_caja(caja: str, custodio: str, cedula: str, politica: dict) -> list[dict]:
    """Contrasta la caja y el custodio contra el catálogo de unidades de negocio."""
    if not politica.get("_catalogo"):
        return []
    info = info_caja(politica, caja)
    if not info:
        return [_h("ALTA", "CAJA_NO_REGISTRADA",
                   f"El código '{caja}' no está en el catálogo de cajas. Verifique el código o registre la unidad.")]
    hs = []
    if not info["activa"]:
        hs.append(_h("ALTA", "CAJA_INACTIVA", f"La caja {caja} ({info['unidad']}) está inactiva en el catálogo."))
    misma_cedula = cedula and info["cedula"] and cedula == info["cedula"]
    if info["responsable"] and custodio and not misma_cedula and _similar(custodio, info["responsable"]) < 0.85:
        hs.append(_h("MEDIA", "CUSTODIO_NO_AUTORIZADO",
                     f"Entrega '{custodio}', pero el responsable registrado de {info['unidad'] or caja} es "
                     f"'{info['responsable']}'."))
    return hs

ORDEN_SEVERIDAD = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}


def _h(severidad, regla, detalle, monto=None, relacionada=None):
    return {"severidad": severidad, "regla": regla, "titulo": REGLAS.get(regla, regla),
            "detalle": detalle, "monto": monto, "factura_relacionada_id": relacionada}


def _similar(a: str, b: str) -> float:
    a, b = normalizar(a), normalizar(b)
    if not a or not b:
        return 0.0
    return 1.0 if a == b or a in b or b in a else SequenceMatcher(None, a, b).ratio()


def _fmt(m) -> str:
    return "—" if m is None else f"₡{m:,.0f}"


def _contiene(texto: str, terminos: list[str]) -> list[str]:
    t = normalizar(texto)
    return [x for x in terminos if normalizar(x) and f" {normalizar(x)}" in f" {t}"]


# ================================================================== facturas

def _total_crc(f: dict, politica: dict) -> float | None:
    if f["total"] is None:
        return None
    if f["moneda"] in ("USD", "US$", "$", "DOLARES", "DÓLARES"):
        return f["total"] * (f["tipo_cambio"] or float(politica.get("tipo_cambio_usd", 500)))
    return f["total"]


def revisar_factura(f: dict, enc: dict, politica: dict) -> list[dict]:
    hs = []
    inst = politica["institucion"]
    lim = politica["limites"]
    comp = politica["comprobantes"]
    alertas = politica.get("alertas", {})
    corte = enc.get("fecha_liquidacion") or date.today()
    total = f["total_crc"]

    faltan = [n for n, v in (("fecha", f["fecha"]), ("proveedor", f["proveedor"]),
                             ("número de factura", f["consecutivo"] or f["clave"]),
                             ("descripción", f["descripcion"]), ("total", f["total"])) if not v]
    if faltan:
        hs.append(_h("ALTA", "COMPROBANTE_INCOMPLETO", "Falta: " + ", ".join(faltan) + "."))

    # --- Datos de la institución como receptor
    ced_inst = solo_digitos(inst.get("cedula_juridica"))
    nombres_inst = [inst.get("nombre", "")] + list(inst.get("nombres_alternativos") or [])
    parecido = max((_similar(f["receptor"], n) for n in nombres_inst), default=0)
    if not f["receptor"] and not f["cedula_receptor"]:
        hs.append(_h("ALTA", "SIN_DATOS_INSTITUCION",
                     "La factura no indica receptor ni cédula. Debe emitirse a nombre de "
                     f"{inst.get('nombre')} (cédula {inst.get('cedula_juridica')})."))
    elif f["cedula_receptor"] and ced_inst and f["cedula_receptor"] != ced_inst:
        hs.append(_h("ALTA", "RECEPTOR_INCORRECTO",
                     f"Cédula del receptor {f['cedula_receptor']} ≠ cédula de la institución {ced_inst}."))
    elif not f["cedula_receptor"]:
        sev = "ALTA" if parecido < 0.85 else "MEDIA"
        hs.append(_h(sev, "SIN_DATOS_INSTITUCION",
                     f"No se registró la cédula del receptor (receptor: '{f['receptor']}')."))
    elif f["receptor"] and parecido < 0.85:
        hs.append(_h("BAJA", "NOMBRE_RECEPTOR_DIFERENTE",
                     f"La cédula coincide pero el nombre '{f['receptor']}' difiere de '{inst.get('nombre')}'."))

    # --- Comprobante electrónico
    tipo = f["tipo_doc"]
    if comp.get("exigir_factura_electronica", True):
        if clave_ilegible(f["clave_original"]):
            hs.append(_h("MEDIA", "CLAVE_ILEGIBLE",
                         f"La clave '{f['clave_original']}' se guardó como número y perdió dígitos. "
                         "Formatee la columna como Texto y vuelva a digitarla."))
        elif not f["clave"]:
            hs.append(_h("ALTA", "SIN_CLAVE", "No se indicó la clave numérica de 50 dígitos."))
        else:
            partes = descomponer_clave(f["clave"])
            if not partes:
                hs.append(_h("ALTA", "CLAVE_INVALIDA",
                             f"La clave tiene {len(f['clave'])} dígitos (deben ser 50)."))
            else:
                tipo = tipo or partes["tipo_documento"]
                if partes["tipo_documento"] != tipo:
                    tipo = partes["tipo_documento"]
                difs = []
                if partes["pais"] != "506":
                    difs.append(f"código de país {partes['pais']}")
                if f["fecha"] and partes["fecha"] and partes["fecha"] != f["fecha"]:
                    difs.append(f"fecha en clave {partes['fecha']:%d/%m/%Y} vs digitada {f['fecha']:%d/%m/%Y}")
                if f["consecutivo"] and f["consecutivo"].isdigit() and len(f["consecutivo"]) == 20 \
                        and f["consecutivo"] != partes["consecutivo"]:
                    difs.append("consecutivo distinto al de la clave")
                if difs:
                    hs.append(_h("MEDIA", "INCONSISTENCIA_CLAVE", "; ".join(difs) + "."))
                if f["cedula_proveedor"] and partes["cedula_emisor"] != f["cedula_proveedor"].lstrip("0"):
                    hs.append(_h("ALTA", "INCONSISTENCIA_CLAVE",
                                 f"La clave pertenece al emisor {partes['cedula_emisor']}, "
                                 f"no al proveedor declarado {f['cedula_proveedor']}."))
                if not f["consecutivo"]:
                    f["consecutivo"] = partes["consecutivo"]
        aceptados = [str(t).zfill(2) for t in comp.get("tipos_documento_aceptados", ["01"])]
        if tipo and tipo not in aceptados:
            nombre = TIPOS_DOCUMENTO.get(tipo, f"tipo {tipo}")
            extra = " El tiquete no identifica al receptor." if tipo == "04" else ""
            hs.append(_h("ALTA", "TIPO_DOCUMENTO", f"{nombre} no es aceptado para liquidar.{extra}"))
    f["tipo_doc"] = tipo

    # --- Montos
    if total is not None and total <= 0:
        hs.append(_h("ALTA", "MONTO_INVALIDO", f"Total {_fmt(total)}."))
    if total is not None and total > lim["monto_maximo_por_factura"]:
        hs.append(_h("ALTA", "EXCEDE_LIMITE",
                     f"{_fmt(total)} supera el máximo de {_fmt(lim['monto_maximo_por_factura'])} por gasto.", total))
    if f["subtotal"] is not None and f["iva"] is not None and f["total"] is not None:
        diferencia = f["subtotal"] + f["iva"] - f["total"]
        if abs(diferencia) > comp.get("tolerancia_calculo", 5):
            hs.append(_h("MEDIA", "ERROR_CALCULO",
                         f"{_fmt(f['subtotal'])} + {_fmt(f['iva'])} = {_fmt(f['subtotal'] + f['iva'])}, "
                         f"pero el total es {_fmt(f['total'])}."))
        if f["subtotal"] > 0 and f["iva"] > 0:
            tasa = f["iva"] / f["subtotal"] * 100
            if min(abs(tasa - t) for t in comp.get("tasas_iva_validas", [13])) > 0.6:
                hs.append(_h("MEDIA", "TASA_IVA", f"El IVA equivale a {tasa:.1f}% del subtotal."))
    if alertas.get("marcar_montos_redondos") and total and total >= alertas.get("monto_redondo_multiplo", 5000) \
            and total % alertas.get("monto_redondo_multiplo", 5000) == 0:
        hs.append(_h("BAJA", "MONTO_REDONDO", f"{_fmt(total)} es un monto exacto; verifique el comprobante original."))

    # --- Fechas
    if f["fecha"]:
        if f["fecha"] > corte:
            hs.append(_h("ALTA", "FECHA_FUTURA", f"Factura del {f['fecha']:%d/%m/%Y}, liquidación del {corte:%d/%m/%Y}."))
        elif (corte - f["fecha"]).days > lim["antiguedad_maxima_factura_dias"]:
            hs.append(_h("MEDIA", "FACTURA_VENCIDA",
                         f"Tiene {(corte - f['fecha']).days} días (máximo {lim['antiguedad_maxima_factura_dias']})."))
        if enc.get("periodo_desde") and enc.get("periodo_hasta") and \
                not (enc["periodo_desde"] <= f["fecha"] <= enc["periodo_hasta"]):
            hs.append(_h("MEDIA", "FUERA_DE_PERIODO",
                         f"Período {enc['periodo_desde']:%d/%m/%Y}–{enc['periodo_hasta']:%d/%m/%Y}."))
        if alertas.get("marcar_fin_de_semana") and f["fecha"].weekday() >= 5:
            dia = "sábado" if f["fecha"].weekday() == 5 else "domingo"
            hs.append(_h("BAJA", "FIN_DE_SEMANA", f"Gasto realizado un {dia}."))

    # --- Naturaleza del gasto
    permitidas = [normalizar(c) for c in politica.get("categorias_permitidas", [])]
    if not f["categoria"]:
        hs.append(_h("MEDIA", "CATEGORIA_NO_AUTORIZADA", "No se indicó la categoría del gasto."))
    elif permitidas and normalizar(f["categoria"]) not in permitidas:
        hs.append(_h("MEDIA", "CATEGORIA_NO_AUTORIZADA", f"'{f['categoria']}' no está en la lista de la política."))
    texto_gasto = f"{f['descripcion']} {f['proveedor']}"
    prohibidos = _contiene(texto_gasto, politica.get("conceptos_prohibidos", []))
    if prohibidos:
        hs.append(_h("ALTA", "GASTO_PROHIBIDO", "Contiene: " + ", ".join(prohibidos) + "."))
    sensibles = _contiene(texto_gasto, politica.get("conceptos_sensibles", []))
    if sensibles and not prohibidos:
        hs.append(_h("MEDIA", "REQUIERE_JUSTIFICACION",
                     "Contiene: " + ", ".join(sensibles) + ". Adjunte justificación del fin institucional."))

    # --- Control interno
    custodio = enc.get("custodio", "")
    aprobadores = (info_caja(politica, enc.get("caja", "")) or {}).get("aprobadores") or []
    if not f["autorizado_por"]:
        hs.append(_h("MEDIA", "SIN_AUTORIZACION", "No se indicó quién aprobó el gasto."))
    elif aprobadores and max(_similar(f["autorizado_por"], a) for a in aprobadores) < 0.85:
        hs.append(_h("MEDIA", "APROBADOR_NO_AUTORIZADO",
                     f"Aprobó '{f['autorizado_por']}'; los aprobadores autorizados de esta caja son: "
                     f"{', '.join(aprobadores)}."))
    elif _similar(f["autorizado_por"], f["solicitado_por"]) >= 0.9 or _similar(f["autorizado_por"], custodio) >= 0.9:
        hs.append(_h("MEDIA", "AUTOAPROBACION", f"Aprobado por {f['autorizado_por']}, quien solicita o custodia el fondo."))
    if (enc.get("cedula_custodio") and f["cedula_proveedor"] == enc["cedula_custodio"]) or \
            _similar(f["proveedor"], custodio) >= 0.9 or _similar(f["proveedor"], f["solicitado_por"]) >= 0.9:
        hs.append(_h("ALTA", "CONFLICTO_INTERES", f"El proveedor '{f['proveedor']}' coincide con el custodio o solicitante."))
    return hs


# ================================================================== duplicados

def _descripcion_hist(h: dict) -> str:
    return (f"liquidación N° {h.get('liquidacion_numero')} de la caja {h.get('caja')} "
            f"(factura del {h.get('fecha') or 's/f'}, {_fmt(h.get('total_crc'))})")


def detectar_duplicados(facturas: list[dict], historico: list[dict], politica: dict) -> None:
    """Agrega hallazgos de duplicidad a cada factura nueva, comparando dentro del archivo y contra el histórico."""
    marcados = set()

    def proveedor_id(x):
        return x.get("cedula_proveedor") or normalizar(x.get("proveedor"))

    def registrar(i, hallazgo, pareja):
        if pareja in marcados:
            return
        marcados.add(pareja)
        facturas[i]["hallazgos"].append(hallazgo)

    hist = []
    for h in historico:
        h = dict(h)
        h["fecha"] = fecha(h.get("fecha"))
        hist.append(h)

    for i, f in enumerate(facturas):
        pid = proveedor_id(f)
        # 1) Dentro del mismo archivo
        for j in range(i):
            g = facturas[j]
            misma_clave = f["clave"] and len(f["clave"]) == 50 and f["clave"] == g["clave"]
            mismo_numero = f["consecutivo"] and f["consecutivo"] == g["consecutivo"] and pid and pid == proveedor_id(g)
            if misma_clave or mismo_numero:
                registrar(i, _h("ALTA", "DUPLICADO_EXACTO",
                                f"Es la misma factura de la fila {g['fila']} de esta liquidación "
                                f"({'misma clave' if misma_clave else 'mismo proveedor y número'}). "
                                "Se estaría reintegrando dos veces.", f["total_crc"]), ("L", i, j))
            elif pid and pid == proveedor_id(g) and f["fecha"] == g["fecha"] and f["total_crc"] == g["total_crc"]:
                registrar(i, _h("MEDIA", "POSIBLE_DUPLICADO",
                                f"Mismo proveedor, fecha y monto que la fila {g['fila']} con distinto número "
                                f"({g['consecutivo']} / {f['consecutivo']}). Confirme que son compras distintas.",
                                f["total_crc"]), ("L", i, j))
            elif f["consecutivo"] and f["consecutivo"] == g["consecutivo"] and f["total_crc"] == g["total_crc"]:
                registrar(i, _h("MEDIA", "POSIBLE_DUPLICADO",
                                f"Mismo número y monto que la fila {g['fila']} pero con otro proveedor "
                                f"('{g['proveedor']}'). Posible alteración del comprobante.", f["total_crc"]), ("L", i, j))
            elif pid and pid == proveedor_id(g) and f["total_crc"] == g["total_crc"] and f["fecha"] and g["fecha"] \
                    and abs((f["fecha"] - g["fecha"]).days) <= 7:
                registrar(i, _h("BAJA", "COMPRA_REPETIDA",
                                f"Mismo proveedor y monto que la fila {g['fila']} en menos de 7 días.", f["total_crc"]), ("L", i, j))

        # 2) Contra liquidaciones anteriores (un solo hallazgo por liquidación previa)
        for h in hist:
            misma_clave = f["clave"] and len(f["clave"]) == 50 and f["clave"] == h.get("clave")
            mismo_numero = f["consecutivo"] and f["consecutivo"] == h.get("consecutivo") and pid and pid == proveedor_id(h)
            previa = ("H", i, h.get("liquidacion_id"))
            if misma_clave or mismo_numero:
                registrar(i, _h("ALTA", "DUPLICADO_EXACTO",
                                f"Esta factura ya fue presentada en la {_descripcion_hist(h)}. "
                                "Reintegro doble.", f["total_crc"], h["id"]), previa)
            elif pid and pid == proveedor_id(h) and f["fecha"] == h["fecha"] and f["total_crc"] == h.get("total_crc"):
                registrar(i, _h("MEDIA", "POSIBLE_DUPLICADO",
                                f"Mismo proveedor, fecha y monto que una factura de la {_descripcion_hist(h)} "
                                "con distinto número.", f["total_crc"], h["id"]), previa)
            elif f["consecutivo"] and f["consecutivo"] == h.get("consecutivo") and f["total_crc"] == h.get("total_crc"):
                registrar(i, _h("MEDIA", "POSIBLE_DUPLICADO",
                                f"Mismo número y monto que una factura del proveedor '{h.get('proveedor')}' en la "
                                f"{_descripcion_hist(h)}.", f["total_crc"], h["id"]), previa)


def detectar_fraccionamiento(facturas: list[dict], historico: list[dict], caja: str, politica: dict) -> list[dict]:
    lim = politica["limites"]
    tope = lim.get("monto_maximo_por_proveedor_dia", lim["monto_maximo_por_factura"])
    ventana = lim.get("ventana_fraccionamiento_dias", 3)
    universo = [("N", f) for f in facturas if f["fecha"] and f["total_crc"]] + \
               [("H", {**h, "fecha": fecha(h.get("fecha"))}) for h in historico if h.get("caja") == caja]
    por_proveedor = defaultdict(list)
    vistas = set()
    for origen, f in universo:
        firma = f.get("clave") or (f.get("cedula_proveedor") or normalizar(f.get("proveedor")), f.get("consecutivo"))
        if firma in vistas:
            continue  # los duplicados ya se reportan aparte; no son compras distintas
        vistas.add(firma)
        if f.get("fecha") and f.get("total_crc"):
            clave = f.get("cedula_proveedor") or normalizar(f.get("proveedor"))
            if clave:
                por_proveedor[clave].append((origen, f))
    hallazgos = []
    for items in por_proveedor.values():
        nuevos = [f for o, f in items if o == "N"]
        if not nuevos:
            continue
        for f in nuevos:
            grupo = [g for _, g in items if abs((g["fecha"] - f["fecha"]).days) <= ventana]
            suma = sum(g["total_crc"] for g in grupo)
            if len(grupo) >= 2 and suma > tope and all(g["total_crc"] <= lim["monto_maximo_por_factura"] for g in grupo):
                filas = sorted({g.get("fila") for g in grupo if g in nuevos and g.get("fila")})
                hallazgos.append(_h("MEDIA", "FRACCIONAMIENTO",
                                    f"{len(grupo)} compras a '{f['proveedor']}' en {ventana} días suman {_fmt(suma)}, "
                                    f"sobre el tope de {_fmt(tope)}. Filas de esta liquidación: "
                                    f"{', '.join(map(str, filas)) or '—'}.", suma))
                break  # un hallazgo por proveedor
    return hallazgos


# ================================================================== liquidación

def revisar_liquidacion(liq: dict, politica: dict, historico: list[dict]) -> dict:
    enc = liq["encabezado"]
    facturas = liq["facturas"]
    for f in facturas:
        f["total_crc"] = _total_crc(f, politica)
        f["hallazgos"] = revisar_factura(f, enc, politica)
    detectar_duplicados(facturas, historico, politica)

    generales = verificar_caja(enc["caja"], enc["custodio"], enc["cedula_custodio"], politica)
    generales += detectar_fraccionamiento(facturas, historico, enc["caja"], politica)
    total = sum(f["total_crc"] or 0 for f in facturas)
    fondo = fondo_de_caja(politica, enc["caja"])
    if not enc["custodio"]:
        generales.append(_h("MEDIA", "SIN_CUSTODIO", "Indique el nombre del custodio del fondo."))
    if enc["monto_solicitado"] is not None and abs(enc["monto_solicitado"] - total) > 1:
        generales.append(_h("ALTA", "DIFERENCIA_REINTEGRO",
                            f"Se solicita {_fmt(enc['monto_solicitado'])} pero las facturas suman {_fmt(total)} "
                            f"(diferencia {_fmt(enc['monto_solicitado'] - total)}).",
                            enc["monto_solicitado"] - total))
    if fondo and total > fondo:
        generales.append(_h("ALTA", "EXCEDE_FONDO", f"Las facturas suman {_fmt(total)} y el fondo es {_fmt(fondo)}.", total))
    minimo = politica["limites"].get("porcentaje_minimo_para_liquidar", 0)
    if fondo and minimo and total / fondo * 100 < minimo:
        generales.append(_h("BAJA", "LIQUIDACION_ANTICIPADA",
                            f"Se liquida el {total / fondo * 100:.0f}% del fondo (mínimo {minimo}%)."))

    for f in facturas:
        f["hallazgos"].sort(key=lambda h: ORDEN_SEVERIDAD[h["severidad"]])
        sevs = {h["severidad"] for h in f["hallazgos"]}
        f["estado"] = "RECHAZADA" if "ALTA" in sevs else "OBSERVADA" if "MEDIA" in sevs else "OK"

    rechazadas = [f for f in facturas if f["estado"] == "RECHAZADA"]
    observadas = [f for f in facturas if f["estado"] == "OBSERVADA"]
    alta_general = any(h["severidad"] == "ALTA" for h in generales)
    estado = "CON RECHAZOS" if rechazadas or alta_general else "CON OBSERVACIONES" if observadas or generales else "APROBABLE"
    return {
        "encabezado": enc,
        "facturas": facturas,
        "hallazgos_generales": generales,
        "resumen": {
            "total": total,
            "fondo": fondo,
            "n_facturas": len(facturas),
            "n_rechazadas": len(rechazadas),
            "n_observadas": len(observadas),
            "monto_rechazado": sum(f["total_crc"] or 0 for f in rechazadas),
            "monto_observado": sum(f["total_crc"] or 0 for f in observadas),
            "monto_aprobable": sum(f["total_crc"] or 0 for f in facturas if f["estado"] != "RECHAZADA"),
            "estado": estado,
        },
    }


# ================================================================== arqueo

def revisar_arqueo(a: dict, politica: dict, historico: list[dict]) -> dict:
    lim = politica["limites"]
    hs = verificar_caja(a["caja"], a["custodio"], "", politica)
    fondo_asignado = fondo_de_caja(politica, a["caja"])
    fondo = a["fondo"] or fondo_asignado
    corte = a["fecha"] or date.today()
    contabilizado = a["efectivo"] + a["pendientes_facturas"] + a["vales"]
    diferencia = contabilizado - fondo
    tolerancia = lim.get("tolerancia_arqueo", 0)

    if diferencia < -tolerancia:
        hs.append(_h("ALTA", "FALTANTE_ARQUEO",
                     f"Efectivo {_fmt(a['efectivo'])} + facturas {_fmt(a['pendientes_facturas'])} + vales "
                     f"{_fmt(a['vales'])} = {_fmt(contabilizado)}; fondo {_fmt(fondo)}. Faltan {_fmt(-diferencia)}.",
                     diferencia))
    elif diferencia > tolerancia:
        hs.append(_h("MEDIA", "SOBRANTE_ARQUEO",
                     f"Sobran {_fmt(diferencia)} respecto al fondo de {_fmt(fondo)}. "
                     "Un sobrante también indica registros incompletos.", diferencia))
    if a["fondo"] and fondo_asignado and abs(a["fondo"] - fondo_asignado) > 1:
        hs.append(_h("MEDIA", "FONDO_DIFERENTE",
                     f"Se declaró {_fmt(a['fondo'])}; la política asigna {_fmt(fondo_asignado)} a la caja {a['caja']}."))
    if not a["realizado_por"] or _similar(a["realizado_por"], a["custodio"]) >= 0.9:
        hs.append(_h("MEDIA", "ARQUEO_NO_INDEPENDIENTE",
                     "El arqueo debe hacerlo una persona distinta al custodio." if a["realizado_por"]
                     else "No se indicó quién realizó el arqueo."))

    claves_hist = {h["clave"]: h for h in historico if h.get("clave")}
    numeros_hist = {(h.get("consecutivo"), round(h.get("total_crc") or 0)): h for h in historico if h.get("consecutivo")}
    for p in a["detalle_pendientes"]:
        es_vale = "VALE" in normalizar(p["tipo"]) or "ADELANTO" in normalizar(p["tipo"])
        if p["fecha"]:
            dias = (corte - p["fecha"]).days
            if es_vale and dias > lim.get("dias_maximos_vale_pendiente", 5):
                hs.append(_h("MEDIA", "VALE_VENCIDO",
                             f"Vale a {p['beneficiario'] or 's/n'} por {_fmt(p['monto'])} con {dias} días sin liquidar.", p["monto"]))
            elif not es_vale and dias > lim["antiguedad_maxima_factura_dias"]:
                hs.append(_h("MEDIA", "PENDIENTE_VENCIDO",
                             f"Factura {p['numero'] or p['clave'][-10:]} de {p['beneficiario']} con {dias} días sin liquidar.", p["monto"]))
        previa = claves_hist.get(p["clave"]) if p["clave"] else None
        previa = previa or numeros_hist.get((p["numero"], round(p["monto"] or 0)))
        if previa and not es_vale:
            hs.append(_h("ALTA", "PENDIENTE_YA_LIQUIDADO",
                         f"La factura {p['numero'] or p['clave']} ({_fmt(p['monto'])}) se cuenta como pendiente, pero ya "
                         f"se reintegró en la {_descripcion_hist(previa)}. El arqueo estaría inflado.", p["monto"], previa["id"]))

    hs.sort(key=lambda h: ORDEN_SEVERIDAD[h["severidad"]])
    sevs = {h["severidad"] for h in hs}
    return {**a, "fondo": fondo, "diferencia": diferencia, "hallazgos": hs,
            "estado": "CON HALLAZGOS GRAVES" if "ALTA" in sevs else "CON OBSERVACIONES" if "MEDIA" in sevs else "CUADRADO"}
