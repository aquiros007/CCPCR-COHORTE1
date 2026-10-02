"""Verificación de cada envío con el mismo cruce que usa el agente (cajachica/comprobantes.py)."""
import os
from datetime import date

from cajachica.comprobantes import NO_CUMPLE, cruzar, estado_general, leer_pdf_bytes, leer_xml_bytes
from cajachica.config import cargar_politica
from cajachica.respaldo import MESES, _limpio, cedula_con_guiones
from cajachica.util import descomponer_clave, solo_digitos

_politica = None


def politica() -> dict:
    global _politica
    if _politica is None:
        _politica = cargar_politica()
        inst = _politica["institucion"]
        inst["nombre"] = os.environ.get("INSTITUCION_NOMBRE", inst.get("nombre"))
        inst["cedula_juridica"] = os.environ.get("INSTITUCION_CEDULA", inst.get("cedula_juridica"))
        # En el portal el proveedor ya está identificado por su cuenta; su aprobación se evalúa aparte.
        _politica.setdefault("proveedores", {})["exigir_proveedor_aprobado"] = True
    return _politica


class EnvioInvalido(Exception):
    pass


def analizar(pdf: bytes, nombre_pdf: str, xml: bytes, respuesta: bytes, proveedor: dict) -> dict:
    fac, resp = leer_xml_bytes(xml), leer_xml_bytes(respuesta)
    if fac.get("tipo") != "factura":
        raise EnvioInvalido("El archivo de la casilla «XML de la factura» no es una factura electrónica de Hacienda."
                            + (" Parece la respuesta de Hacienda: cámbielo de casilla." if fac.get("tipo") == "respuesta" else ""))
    if resp.get("tipo") != "respuesta":
        raise EnvioInvalido("El archivo de la casilla «Respuesta de Hacienda» no es un MensajeHacienda."
                            + (" Es la aceptación del receptor, no la respuesta de Hacienda." if resp.get("tipo") == "mensaje_receptor" else ""))
    if len(fac["clave"]) != 50:
        raise EnvioInvalido("La factura no trae una clave numérica válida de 50 dígitos.")
    if solo_digitos(fac["emisor_cedula"]).lstrip("0") != solo_digitos(proveedor["cedula"]).lstrip("0"):
        raise EnvioInvalido(f"La factura la emitió la cédula {fac['emisor_cedula']}, no la suya "
                            f"({proveedor['cedula']}). Solo puede enviar facturas propias.")
    pdf_datos = leer_pdf_bytes(pdf, nombre_pdf)
    registro = {solo_digitos(proveedor["cedula"]): {"estado": proveedor["estado"], "razon_social": proveedor["razon_social"]}}
    controles = cruzar(fac["clave"], fac, resp, pdf_datos, politica(), registro, duplicada=False)
    misma = resp["clave"] == fac["clave"]
    controles.insert(2, {"control": "La respuesta de Hacienda corresponde a la factura", "estado": "CUMPLE" if misma else NO_CUMPLE,
                         "detalle": "Misma clave." if misma else "La respuesta trae otra clave."})
    f = fac["fecha"] or (descomponer_clave(fac["clave"]) or {}).get("fecha") or date.today()
    return {
        "factura": fac, "respuesta": resp, "controles": controles, "cruce": estado_general(controles, vencido=True),
        "carpeta": [str(f.year), MESES[f.month - 1],
                    f"{cedula_con_guiones(fac['emisor_cedula'])} {_limpio(fac['emisor_nombre'])}".strip(),
                    fac["consecutivo"] or fac["clave"][21:41]],
    }
