"""Normalización de datos: montos, fechas, textos, cédulas y clave de factura electrónica (CR)."""
import re
import unicodedata
from datetime import date, datetime

import pandas as pd


def texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and pd.isna(valor):
        return ""
    s = str(valor).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def normalizar(valor) -> str:
    """Mayúsculas, sin tildes, sin puntuación ni sufijos societarios, espacios simples."""
    s = unicodedata.normalize("NFKD", texto(valor)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s.upper())
    s = re.sub(r"\b(S ?A|SRL|S R L|LTDA|LIMITADA|SOCIEDAD ANONIMA|INC|LLC)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def solo_digitos(valor) -> str:
    s = texto(valor)
    # Un número leído por Excel puede venir como "3101123456.0"
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return re.sub(r"\D", "", s)


def monto(valor) -> float | None:
    """Acepta 12500, '12,500.00', '12.500,00', '₡ 12 500', '$1,200.50'."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r"[^\d,.\-]", "", texto(valor))
    if not s or s in "-.,":
        return None
    if "," in s and "." in s:
        # El último separador es el decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        s = s.replace(",", ".") if len(partes) == 2 and len(partes[1]) in (1, 2) else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s and len(s.split(".")[1]) == 3:
        s = s.replace(".", "")  # 12.500 -> miles
    try:
        return float(s)
    except ValueError:
        return None


def fecha(valor) -> date | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)) and 20000 < valor < 80000:  # serial de Excel
        return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(valor))).date()
    s = texto(valor)
    if not s:
        return None
    iso = re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", s)
    try:
        ts = pd.to_datetime(s, dayfirst=not iso, errors="coerce")
    except (ValueError, TypeError):
        return None
    return None if pd.isna(ts) else ts.date()


def clave_ilegible(valor) -> bool:
    """Excel convierte claves de 50 dígitos en notación científica (5.06E+49) y pierde dígitos."""
    return bool(re.search(r"\d[.,]?\d*E\+?\d+", texto(valor), re.IGNORECASE))


def descomponer_clave(clave: str) -> dict | None:
    """Clave numérica de 50 dígitos del comprobante electrónico de Hacienda (CR).

    506 | DDMMAA | cédula emisor (12) | consecutivo (20) | situación (1) | código seguridad (8)
    El consecutivo = sucursal (3) + terminal (5) + tipo documento (2) + número (10).
    """
    if len(clave) != 50 or not clave.isdigit():
        return None
    try:
        emision = datetime.strptime(clave[3:9], "%d%m%y").date()
    except ValueError:
        emision = None
    consecutivo = clave[21:41]
    return {
        "pais": clave[0:3],
        "fecha": emision,
        "cedula_emisor": clave[9:21].lstrip("0"),
        "consecutivo": consecutivo,
        "tipo_documento": consecutivo[8:10],
        "situacion": clave[41],
    }


TIPOS_DOCUMENTO = {
    "01": "Factura electrónica",
    "02": "Nota de débito",
    "03": "Nota de crédito",
    "04": "Tiquete electrónico",
    "08": "Factura electrónica de compra",
    "09": "Factura electrónica de exportación",
}
