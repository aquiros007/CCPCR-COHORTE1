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
COLUMNAS_CATALOGO = ["Código caja (FUC)", "Unidad ejecutora", "Persona encargada", "Cédula persona encargada",
                     "Persona responsable (titular)", "Monto del fondo", "Aprobadores autorizados",
                     "Correo persona encargada", "Activa"]


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
        codigo = texto(valor(fila, "Código caja (FUC)", "Código caja", "Codigo", "Caja", "FUC"))
        if not codigo:
            continue
        aprobadores = texto(valor(fila, "Aprobadores autorizados", "Aprobador", "Aprobadores"))
        titular = texto(valor(fila, "Persona responsable (titular)", "Persona responsable", "Titular"))
        activa = normalizar(valor(fila, "Activa", "Estado"))
        catalogo[codigo.upper()] = {
            "codigo": codigo.upper(),
            "unidad": texto(valor(fila, "Unidad ejecutora", "Unidad de negocio", "Unidad", "Departamento")),
            "responsable": texto(valor(fila, "Persona encargada", "Responsable (custodio)", "Responsable", "Custodio")),
            "cedula": solo_digitos(valor(fila, "Cédula persona encargada", "Cédula responsable", "Cedula")),
            "titular": titular,
            "fondo": monto(valor(fila, "Monto del fondo", "Fondo", "Monto")),
            "aprobadores": [a.strip() for a in aprobadores.replace(";", ",").split(",") if a.strip()] or
                           ([titular] if titular else []),
            "correo": texto(valor(fila, "Correo persona encargada", "Correo responsable", "Correo")),
            "activa": activa not in ("NO", "INACTIVA", "N", "0", "FALSE"),
        }
    return catalogo


def problemas_catalogo(politica: dict, ruta: Path = RUTA_CATALOGO) -> list[dict]:
    """Reglas de apertura (arts. 4, 5, 13 b): una caja por FUC, una caja por persona encargada, fondo dentro del tope."""
    import pandas as pd

    from .util import normalizar, texto
    if not ruta.exists():
        return []
    df = pd.read_excel(ruta, dtype=object)
    col = {normalizar(c): c for c in df.columns}
    cod_col = next((col[normalizar(n)] for n in ("Código caja (FUC)", "Código caja", "Caja", "FUC") if normalizar(n) in col), None)
    problemas = []
    if cod_col:
        codigos = [texto(c).upper() for c in df[cod_col] if texto(c)]
        for c in sorted({c for c in codigos if codigos.count(c) > 1}):
            problemas.append({"codigo": c, "problema": "FUC repetido en el catálogo (solo una caja chica por FUC)",
                              "articulo": "Arts. 4 y 5"})
    excepciones = {str(x).upper() for x in (politica.get("apertura") or {}).get("excepciones_varias_cajas", [])}
    por_persona = {}
    for c, i in (politica.get("_catalogo") or {}).items():
        if i["activa"] and (i["cedula"] or i["responsable"]):
            por_persona.setdefault(i["cedula"] or normalizar(i["responsable"]), []).append(c)
    for persona, cajas in por_persona.items():
        if len(cajas) > 1 and not set(cajas) & excepciones:
            nombre = politica["_catalogo"][cajas[0]]["responsable"]
            problemas.append({"codigo": ", ".join(cajas), "problema": f"{nombre} es persona encargada de {len(cajas)} cajas "
                              "activas (solo puede tener una abierta a la vez)", "articulo": "Arts. 4 y 5"})
    ap = politica.get("apertura") or {}
    if ap.get("monto_licitacion_reducida"):
        tope = float(ap["monto_licitacion_reducida"]) * float(ap.get("porcentaje_tope_fondo", 10)) / 100
        for c, i in (politica.get("_catalogo") or {}).items():
            if i["fondo"] and i["fondo"] > tope:
                problemas.append({"codigo": c, "problema": f"Fondo ₡{i['fondo']:,.0f} supera el tope de ₡{tope:,.0f}",
                                  "articulo": "Art. 13 b"})
    return problemas


def info_caja(politica: dict, caja: str) -> dict | None:
    return (politica.get("_catalogo") or {}).get(str(caja).upper())
