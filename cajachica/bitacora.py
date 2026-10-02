"""Bitácora de revisión en CSV para el respaldo en Drive.

Toma lo exportado con ArtifactData (`out_dir`) del dashboard y del portal:
  <dir>/accesos/<persona>/meses/<AAAA-MM>.json        ingresos y confirmaciones de vigencia
  <dir>/validaciones/<persona>/meses/<AAAA-MM>.json   validaciones de evidencia
  <dir>/aprobaciones/<persona>/meses/<AAAA-MM>.json   decisiones sobre comprobantes
  <dir>/proveedores/<persona>.json, <dir>/estado_proveedores/<persona>.json   registros del portal
  <dir>/nombres.json (opcional)                       {persona: nombre} resuelto con ArtifactData profiles
"""
import csv
import json
from datetime import datetime
from pathlib import Path

from .config import RUTA_REPORTES


def _datos(ruta: Path) -> dict:
    d = json.loads(ruta.read_text(encoding="utf-8"))
    return d.get("data") if isinstance(d.get("data"), dict) else d


def _escribir(ruta: Path, columnas: list[str], filas: list[list]) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(columnas)
        w.writerows(filas)
    return ruta


def exportar_csv(carpeta: Path) -> list[Path]:
    nombres = json.loads((carpeta / "nombres.json").read_text(encoding="utf-8")) if (carpeta / "nombres.json").exists() else {}
    quien = lambda uid: nombres.get(uid, "")
    sello = datetime.now().strftime("%Y-%m-%d_%H%M")
    destino = RUTA_REPORTES / "bitacora"
    escritos = []

    def eventos(coleccion):
        for archivo in sorted((carpeta / coleccion).glob("*/meses/*.json")):
            uid = archivo.parent.parent.name
            for ev in _datos(archivo).get("eventos", []):
                yield uid, ev

    filas = [[ev.get("ts"), quien(uid), uid, ev.get("tipo"), ev.get("rol"), ev.get("motivo") or ev.get("resultado"),
              ev.get("alcance") or ev.get("comentario"), ev.get("corte")] for uid, ev in eventos("accesos")]
    if filas:
        escritos.append(_escribir(destino / f"Bitacora_accesos_{sello}.csv",
                                  ["Fecha y hora (UTC)", "Persona", "Id de la persona", "Registro", "Rol", "Motivo / resultado",
                                   "Alcance / comentario", "Corte revisado"], sorted(filas)))
    filas = [[ev.get("ts"), quien(uid), uid, ev.get("rol"), ev.get("caja"), ev.get("liquidacion"), ev.get("fila"),
              ev.get("regla"), ev.get("resultado"), ev.get("comentario"), ev.get("clave"), ev.get("corte")]
             for uid, ev in eventos("validaciones")]
    if filas:
        escritos.append(_escribir(destino / f"Bitacora_validaciones_{sello}.csv",
                                  ["Fecha y hora (UTC)", "Persona", "Id de la persona", "Rol", "FUC", "Liquidación", "Fila",
                                   "Regla", "Resultado", "Evidencia y conclusión", "Clave del hallazgo", "Corte revisado"], sorted(filas)))
    filas = [[ev.get("ts"), quien(uid), uid, ev.get("rol"), ev.get("decision"), ev.get("estado_cruce"),
              ev.get("proveedor_cedula"), ev.get("total"), ev.get("comentario"), ev.get("clave"), ev.get("corte")]
             for uid, ev in eventos("aprobaciones")]
    if filas:
        escritos.append(_escribir(destino / f"Bitacora_aprobaciones_{sello}.csv",
                                  ["Fecha y hora (UTC)", "Persona", "Id de la persona", "Rol", "Decisión", "Resultado del cruce",
                                   "Cédula proveedor", "Total", "Fundamento", "Clave de la factura", "Corte revisado"], sorted(filas)))
    estados = {a.stem: _datos(a) for a in (carpeta / "estado_proveedores").glob("*.json")}
    filas = [[_datos(a).get("ts"), _datos(a).get("cedula"), _datos(a).get("razon_social"), _datos(a).get("correo"),
              _datos(a).get("telefono"), (estados.get(a.stem) or {}).get("estado", "Pendiente"), a.stem]
             for a in sorted((carpeta / "proveedores").glob("*.json"))]
    if filas:
        escritos.append(_escribir(destino / f"Registro_portal_proveedores_{sello}.csv",
                                  ["Registrado (UTC)", "Cédula", "Razón social", "Correo", "Teléfono", "Estado", "Id de la persona"], filas))
    return escritos
