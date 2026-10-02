"""Carga de la política y resolución de rutas del repositorio."""
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
RUTA_POLITICA = RAIZ / "config" / "politica.yaml"
RUTA_DB = RAIZ / "data" / "cajachica.db"
RUTA_REPORTES = RAIZ / "reportes"

SUBCARPETAS = {
    "plantillas": "00_Plantillas",
    "entrada": "01_Entrada",
    "procesados": "02_Procesados",
    "revisiones": "03_Revisiones",
    "rechazados": "04_Rechazados",
    "dashboard": "05_Dashboard",
    "informes": "06_Informes",
}


RUTA_POLITICA_EJEMPLO = RAIZ / "config" / "politica.ejemplo.yaml"


def cargar_politica(ruta: Path = RUTA_POLITICA) -> dict:
    """Usa config/politica.yaml (la real, fuera del control de versiones) o, si no existe, la de ejemplo."""
    if not ruta.exists():
        ruta = RUTA_POLITICA_EJEMPLO
    with open(ruta, encoding="utf-8") as f:
        politica = yaml.safe_load(f)
    politica["_catalogo"] = cargar_catalogo()
    return politica


def ruta_repositorio(politica: dict) -> Path:
    ruta = Path(str(politica.get("repositorio", "./repositorio"))).expanduser()
    return ruta if ruta.is_absolute() else (RAIZ / ruta).resolve()


def carpetas(politica: dict, crear: bool = True) -> dict:
    base = ruta_repositorio(politica)
    rutas = {clave: base / nombre for clave, nombre in SUBCARPETAS.items()}
    if crear:
        for ruta in rutas.values():
            ruta.mkdir(parents=True, exist_ok=True)
        RUTA_DB.parent.mkdir(parents=True, exist_ok=True)
        RUTA_REPORTES.mkdir(parents=True, exist_ok=True)
    return rutas


def fondo_de_caja(politica: dict, caja: str) -> float:
    info = info_caja(politica, caja)
    if info and info.get("fondo"):
        return float(info["fondo"])
    fondos = politica.get("fondos") or {}
    return float(fondos.get(caja, fondos.get("DEFAULT", 0)) or 0)


# ------------------------------------------------------------------ catálogo de unidades de negocio

RUTA_CATALOGO = RAIZ / "config" / "Catalogo_Cajas.xlsx"
COLUMNAS_CATALOGO = ["Código caja", "Unidad de negocio", "Responsable (custodio)", "Cédula responsable",
                     "Monto del fondo", "Aprobadores autorizados", "Correo responsable", "Activa"]


def cargar_catalogo(ruta: Path = RUTA_CATALOGO) -> dict:
    """{código: {unidad, responsable, cedula, fondo, aprobadores[], correo, activa}} desde Excel o CSV."""
    import pandas as pd

    from .util import monto, normalizar, solo_digitos, texto

    if not ruta.exists():
        csv = ruta.with_suffix(".csv")
        if not csv.exists():
            return {}
        ruta = csv
    df = pd.read_csv(ruta, dtype=str, sep=None, engine="python", encoding="utf-8-sig") if ruta.suffix == ".csv" \
        else pd.read_excel(ruta, dtype=object)
    col = {normalizar(c): c for c in df.columns}

    def valor(fila, *nombres):
        for n in nombres:
            if normalizar(n) in col:
                return fila[col[normalizar(n)]]
        return None

    catalogo = {}
    for _, fila in df.iterrows():
        codigo = texto(valor(fila, "Código caja", "Codigo", "Caja"))
        if not codigo:
            continue
        aprobadores = texto(valor(fila, "Aprobadores autorizados", "Aprobador", "Aprobadores"))
        activa = normalizar(valor(fila, "Activa", "Estado"))
        catalogo[codigo.upper()] = {
            "codigo": codigo.upper(),
            "unidad": texto(valor(fila, "Unidad de negocio", "Unidad", "Departamento")),
            "responsable": texto(valor(fila, "Responsable (custodio)", "Responsable", "Custodio")),
            "cedula": solo_digitos(valor(fila, "Cédula responsable", "Cedula")),
            "fondo": monto(valor(fila, "Monto del fondo", "Fondo", "Monto")),
            "aprobadores": [a.strip() for a in aprobadores.replace(";", ",").split(",") if a.strip()],
            "correo": texto(valor(fila, "Correo responsable", "Correo")),
            "activa": activa not in ("NO", "INACTIVA", "N", "0", "FALSE"),
        }
    return catalogo


def info_caja(politica: dict, caja: str) -> dict | None:
    return (politica.get("_catalogo") or {}).get(str(caja).upper())
