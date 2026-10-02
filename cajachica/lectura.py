"""Lectura de liquidaciones y arqueos desde Excel o CSV, con reconocimiento flexible de columnas."""
from pathlib import Path

import pandas as pd

from .util import fecha, monto, normalizar, solo_digitos, texto


class ErrorLectura(Exception):
    pass


def _alias(*nombres):
    return {normalizar(n) for n in nombres}


COLUMNAS_FACTURA = {
    "fecha": _alias("fecha factura", "fecha de factura", "fecha", "fecha emision", "fecha de emision"),
    "tipo_doc": _alias("tipo documento", "tipo de documento", "tipo doc", "tipo comprobante"),
    "clave": _alias("clave", "clave numerica", "clave de factura", "clave hacienda"),
    "consecutivo": _alias("numero factura", "numero de factura", "n factura", "no factura", "nº factura",
                          "n° factura", "consecutivo", "numero consecutivo", "factura", "comprobante"),
    "proveedor": _alias("proveedor", "emisor", "nombre proveedor", "nombre del proveedor", "comercio"),
    "cedula_proveedor": _alias("cedula proveedor", "cedula del proveedor", "identificacion proveedor",
                               "cedula emisor", "id proveedor"),
    "receptor": _alias("receptor", "nombre receptor", "a nombre de", "cliente", "facturado a"),
    "cedula_receptor": _alias("cedula receptor", "identificacion receptor", "cedula cliente",
                              "cedula juridica receptor"),
    "descripcion": _alias("descripcion", "descripcion del gasto", "detalle", "concepto", "detalle del gasto"),
    "categoria": _alias("categoria", "cuenta", "rubro", "partida", "tipo de gasto"),
    "subtotal": _alias("subtotal", "monto sin iva", "base imponible"),
    "iva": _alias("iva", "impuesto", "impuesto de ventas", "monto iva"),
    "total": _alias("total", "monto", "total factura", "monto total", "total comprobante"),
    "moneda": _alias("moneda",),
    "tipo_cambio": _alias("tipo de cambio", "tipo cambio", "tc"),
    "solicitado_por": _alias("solicitado por", "solicitante", "beneficiario", "funcionario"),
    "autorizado_por": _alias("autorizado por", "aprobado por", "autoriza", "aprobador"),
}

COLUMNAS_LIQUIDACION = {
    "caja": _alias("caja", "codigo caja", "caja chica", "centro de costo", "departamento"),
    "custodio": _alias("custodio", "responsable", "encargado", "responsable de caja"),
    "cedula_custodio": _alias("cedula custodio", "cedula del custodio", "cedula responsable"),
    "numero": _alias("numero de liquidacion", "numero liquidacion", "n liquidacion", "liquidacion", "no liquidacion"),
    "fecha_liquidacion": _alias("fecha de liquidacion", "fecha liquidacion"),
    "monto_solicitado": _alias("monto solicitado", "monto a reintegrar", "reintegro solicitado", "monto solicitado reintegro"),
    "periodo_desde": _alias("periodo desde", "desde"),
    "periodo_hasta": _alias("periodo hasta", "hasta"),
}

COLUMNAS_ARQUEO = {
    "caja": COLUMNAS_LIQUIDACION["caja"],
    "custodio": COLUMNAS_LIQUIDACION["custodio"],
    "fecha": _alias("fecha del arqueo", "fecha arqueo", "fecha"),
    "realizado_por": _alias("realizado por", "arqueado por", "revisado por", "auditor"),
    "fondo": _alias("fondo asignado", "fondo", "monto del fondo"),
    "efectivo": _alias("efectivo contado", "efectivo", "total efectivo"),
    "pendientes": _alias("facturas pendientes", "facturas por liquidar", "comprobantes pendientes"),
    "vales": _alias("vales pendientes", "vales", "adelantos"),
}

COLUMNAS_EFECTIVO = {
    "denominacion": _alias("denominacion", "billete moneda", "valor"),
    "cantidad": _alias("cantidad", "unidades"),
    "subtotal": _alias("subtotal", "monto", "total"),
}

COLUMNAS_PENDIENTE = {
    "tipo": _alias("tipo", "tipo de pendiente"),
    "fecha": _alias("fecha",),
    "clave": COLUMNAS_FACTURA["clave"],
    "numero": _alias("numero", "numero factura", "consecutivo", "numero de vale", "documento"),
    "beneficiario": _alias("beneficiario", "proveedor", "funcionario", "a favor de", "beneficiario proveedor"),
    "descripcion": COLUMNAS_FACTURA["descripcion"],
    "monto": _alias("monto", "total", "valor"),
}


def _mapear(encabezados, esquema) -> dict:
    """Devuelve {campo: índice de columna}."""
    mapa = {}
    for i, h in enumerate(encabezados):
        n = normalizar(h)
        for campo, alias in esquema.items():
            if campo not in mapa and n in alias:
                mapa[campo] = i
                break
    return mapa


def _tabla(df_crudo: pd.DataFrame, esquema: dict, minimo: int = 3) -> list[dict]:
    """Ubica la fila de encabezados (puede haber títulos arriba) y devuelve filas como dicts."""
    for i in range(min(20, len(df_crudo))):
        mapa = _mapear(list(df_crudo.iloc[i]), esquema)
        if len(mapa) >= minimo:
            filas = []
            for j in range(i + 1, len(df_crudo)):
                fila = df_crudo.iloc[j]
                registro = {campo: fila.iloc[col] for campo, col in mapa.items()}
                if all(texto(v) == "" for v in registro.values()):
                    continue
                registro["_fila"] = j + 1  # número de fila en Excel
                filas.append(registro)
            return filas
    return []


def _clave_valor(df_crudo: pd.DataFrame, esquema: dict) -> dict:
    """Hoja tipo 'Campo | Valor'."""
    datos = {}
    for _, fila in df_crudo.iterrows():
        valores = [v for v in fila.tolist() if texto(v) != ""]
        if len(valores) < 2:
            continue
        n = normalizar(valores[0])
        for campo, alias in esquema.items():
            if n in alias and campo not in datos:
                datos[campo] = valores[1]
    return datos


def _leer_hojas(ruta: Path) -> dict[str, pd.DataFrame]:
    sufijo = ruta.suffix.lower()
    if sufijo == ".csv":
        for codificacion in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(ruta, header=None, dtype=str, sep=None, engine="python",
                                 encoding=codificacion, keep_default_na=False)
                return {"CSV": df}
            except UnicodeDecodeError:
                continue
        raise ErrorLectura("No se pudo leer el CSV (codificación desconocida).")
    if sufijo in (".xlsx", ".xlsm", ".xls"):
        try:
            return pd.read_excel(ruta, sheet_name=None, header=None, dtype=object)
        except Exception as e:  # archivo dañado, protegido, etc.
            raise ErrorLectura(f"No se pudo abrir el Excel: {e}") from e
    raise ErrorLectura(f"Formato no soportado: {sufijo}. Use .xlsx o .csv")


def _hoja(hojas: dict, *nombres) -> pd.DataFrame | None:
    buscados = {normalizar(n) for n in nombres}
    for nombre, df in hojas.items():
        if normalizar(nombre) in buscados:
            return df
    return None


def tipo_de_archivo(ruta: Path, hojas: dict) -> str:
    nombres = " ".join(normalizar(h) for h in hojas) + " " + normalizar(ruta.stem)
    if "ARQUEO" in nombres or "EFECTIVO" in nombres:
        return "arqueo"
    if len(hojas) == 1:
        df = next(iter(hojas.values()))
        for i in range(min(20, len(df))):
            if len(_mapear(list(df.iloc[i]), COLUMNAS_ARQUEO)) >= 5:
                return "arqueo"
    return "liquidacion"


# ------------------------------------------------------------------ liquidaciones

def _limpiar_factura(f: dict) -> dict:
    return {
        "fila": f.get("_fila"),
        "fecha": fecha(f.get("fecha")),
        "tipo_doc": solo_digitos(f.get("tipo_doc")).zfill(2) if texto(f.get("tipo_doc")) else "",
        "clave_original": texto(f.get("clave")),
        "clave": solo_digitos(f.get("clave")),
        "consecutivo": solo_digitos(f.get("consecutivo")) or texto(f.get("consecutivo")),
        "proveedor": texto(f.get("proveedor")),
        "cedula_proveedor": solo_digitos(f.get("cedula_proveedor")),
        "receptor": texto(f.get("receptor")),
        "cedula_receptor": solo_digitos(f.get("cedula_receptor")),
        "descripcion": texto(f.get("descripcion")),
        "categoria": texto(f.get("categoria")),
        "subtotal": monto(f.get("subtotal")),
        "iva": monto(f.get("iva")),
        "total": monto(f.get("total")),
        "moneda": (texto(f.get("moneda")) or "CRC").upper().replace("₡", "CRC").replace("COLONES", "CRC"),
        "tipo_cambio": monto(f.get("tipo_cambio")),
        "solicitado_por": texto(f.get("solicitado_por")),
        "autorizado_por": texto(f.get("autorizado_por")),
    }


def _limpiar_encabezado(e: dict) -> dict:
    return {
        "caja": (texto(e.get("caja")) or "SIN CAJA").upper(),
        "custodio": texto(e.get("custodio")),
        "cedula_custodio": solo_digitos(e.get("cedula_custodio")),
        "numero": texto(e.get("numero")).removesuffix(".0"),
        "fecha_liquidacion": fecha(e.get("fecha_liquidacion")),
        "monto_solicitado": monto(e.get("monto_solicitado")),
        "periodo_desde": fecha(e.get("periodo_desde")),
        "periodo_hasta": fecha(e.get("periodo_hasta")),
    }


def leer_liquidaciones(ruta: Path, hojas: dict) -> list[dict]:
    hoja_enc = _hoja(hojas, "Encabezado", "Datos generales", "Datos")
    encabezado_hoja = _clave_valor(hoja_enc, COLUMNAS_LIQUIDACION) if hoja_enc is not None else {}

    hoja_fact = _hoja(hojas, "Facturas", "Detalle", "Liquidacion", "Gastos")
    candidatas = [hoja_fact] if hoja_fact is not None else list(hojas.values())
    esquema = {**COLUMNAS_FACTURA, **COLUMNAS_LIQUIDACION}
    filas = []
    for df in candidatas:
        filas = _tabla(df, esquema, minimo=4)
        if filas:
            break
    if not filas:
        raise ErrorLectura("No se encontró la tabla de facturas. Verifique que use la plantilla "
                           "(columnas Fecha factura, Proveedor, Descripción, Total, etc.).")

    grupos: dict[tuple, dict] = {}
    for f in filas:
        enc = _limpiar_encabezado({**encabezado_hoja, **{k: v for k, v in f.items()
                                                         if k in COLUMNAS_LIQUIDACION and texto(v)}})
        if not enc["numero"]:
            enc["numero"] = ruta.stem
        llave = (enc["caja"], enc["numero"])
        grupo = grupos.setdefault(llave, {"encabezado": enc, "facturas": []})
        factura = _limpiar_factura(f)
        if factura["total"] is None and not factura["proveedor"] and not factura["consecutivo"]:
            continue  # fila de totales o vacía
        if normalizar(factura["proveedor"]).startswith("TOTAL") or normalizar(factura["descripcion"]).startswith("TOTAL"):
            continue
        grupo["facturas"].append(factura)
    return [g for g in grupos.values() if g["facturas"]]


# ------------------------------------------------------------------ arqueos

def leer_arqueos(ruta: Path, hojas: dict) -> list[dict]:
    hoja_enc = _hoja(hojas, "Encabezado", "Arqueo", "Datos generales")
    hoja_efe = _hoja(hojas, "Efectivo", "Conteo", "Denominaciones")
    hoja_pen = _hoja(hojas, "Pendientes", "Comprobantes", "Vales")

    if hoja_enc is not None and (hoja_efe is not None or hoja_pen is not None):
        enc = _clave_valor(hoja_enc, COLUMNAS_ARQUEO)
        efectivo_detalle = []
        efectivo = monto(enc.get("efectivo"))
        if hoja_efe is not None:
            for fila in _tabla(hoja_efe, COLUMNAS_EFECTIVO, minimo=2):
                d, c = monto(fila.get("denominacion")), monto(fila.get("cantidad"))
                sub = d * c if d is not None and c is not None else monto(fila.get("subtotal"))
                if sub:
                    efectivo_detalle.append({"denominacion": d, "cantidad": c, "subtotal": sub})
            if efectivo_detalle:
                efectivo = sum(x["subtotal"] for x in efectivo_detalle)
        pendientes = []
        if hoja_pen is not None:
            for fila in _tabla(hoja_pen, COLUMNAS_PENDIENTE, minimo=3):
                m = monto(fila.get("monto"))
                if m is None:
                    continue
                pendientes.append({
                    "tipo": texto(fila.get("tipo")) or "Factura",
                    "fecha": fecha(fila.get("fecha")),
                    "clave": solo_digitos(fila.get("clave")),
                    "numero": solo_digitos(fila.get("numero")) or texto(fila.get("numero")),
                    "beneficiario": texto(fila.get("beneficiario")),
                    "descripcion": texto(fila.get("descripcion")),
                    "monto": m,
                })
        es_vale = lambda p: "VALE" in normalizar(p["tipo"]) or "ADELANTO" in normalizar(p["tipo"])
        return [{
            "caja": (texto(enc.get("caja")) or "SIN CAJA").upper(),
            "custodio": texto(enc.get("custodio")),
            "fecha": fecha(enc.get("fecha")),
            "realizado_por": texto(enc.get("realizado_por")),
            "fondo": monto(enc.get("fondo")),
            "efectivo": efectivo or 0.0,
            "pendientes_facturas": sum(p["monto"] for p in pendientes if not es_vale(p)) or (monto(enc.get("pendientes")) or 0.0),
            "vales": sum(p["monto"] for p in pendientes if es_vale(p)) or (monto(enc.get("vales")) or 0.0),
            "detalle_efectivo": efectivo_detalle,
            "detalle_pendientes": pendientes,
        }]

    # Formato plano (CSV): una fila por arqueo
    arqueos = []
    for df in hojas.values():
        for fila in _tabla(df, COLUMNAS_ARQUEO, minimo=4):
            arqueos.append({
                "caja": (texto(fila.get("caja")) or "SIN CAJA").upper(),
                "custodio": texto(fila.get("custodio")),
                "fecha": fecha(fila.get("fecha")),
                "realizado_por": texto(fila.get("realizado_por")),
                "fondo": monto(fila.get("fondo")),
                "efectivo": monto(fila.get("efectivo")) or 0.0,
                "pendientes_facturas": monto(fila.get("pendientes")) or 0.0,
                "vales": monto(fila.get("vales")) or 0.0,
                "detalle_efectivo": [],
                "detalle_pendientes": [],
            })
        if arqueos:
            break
    if not arqueos:
        raise ErrorLectura("No se reconoció el formato del arqueo. Use la plantilla de arqueo.")
    return arqueos


def leer_archivo(ruta: Path) -> tuple[str, list[dict]]:
    hojas = _leer_hojas(ruta)
    tipo = tipo_de_archivo(ruta, hojas)
    datos = leer_arqueos(ruta, hojas) if tipo == "arqueo" else leer_liquidaciones(ruta, hojas)
    return tipo, datos
