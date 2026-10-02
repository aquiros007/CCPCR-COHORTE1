#!/usr/bin/env python3
"""Agente de control de Caja Chica.

Uso:
  python run.py iniciar      Crea las carpetas del repositorio y las plantillas
  python run.py procesar     Cruza comprobantes de proveedores, revisa todo lo de 01_Entrada y actualiza el dashboard
  python run.py portal       Genera el portal de proveedores (reportes/portal_proveedores.html)
  python run.py importar-web Trae las facturas nuevas del portal web (Railway) y las marca "En revisión"
  python run.py importar-portal <carpeta>
                             Trae al repositorio los envíos exportados del portal (out_dir de ArtifactData)
  python run.py respaldo-pendiente        Lista (JSON) lo que falta respaldar en Google Drive y a qué subcarpeta
  python run.py respaldo-registrar <json> Marca como respaldados los archivos subidos ({ruta, hash, drive_id, ...})
  python run.py respaldo-local <carpeta>  Copia lo pendiente a la carpeta de Google Drive para escritorio
  python run.py respaldo-bitacora <dir>   Convierte la bitácora exportada (out_dir de ArtifactData) a CSV
  python run.py proveedores  Solo cruza los comprobantes de 07_Proveedores (PDF + XML + respuesta de Hacienda)
  python run.py dashboard    Regenera el dashboard desde la base de datos
  python run.py informe [días | desde hasta]
                             Informe de incumplimientos de todas las unidades (por defecto, últimos 7 días)
  python run.py resumen      Imprime (JSON) los datos del período para el análisis ejecutivo
  python run.py demo         Copia archivos de ejemplo con irregularidades a 01_Entrada
"""
import json
import sys
from datetime import date, timedelta

from cajachica.config import RUTA_CATALOGO, RUTA_DB, RUTA_REPORTES, carpetas, cargar_politica
from cajachica.informe import generar_informe
from cajachica.dashboard import generar_dashboard
from cajachica.db import BaseDatos
from cajachica.plantillas import CATALOGO_DEMO, crear_catalogo, crear_demo, crear_plantillas
from cajachica.procesador import procesar


def _dashboard(politica, rutas):
    """El dashboard completo solo se abre desde su enlace oficial, donde cada ingreso queda registrado.
    En el repositorio compartido queda un acceso directo, no una copia con los datos."""
    conf = politica.get("dashboard") or {}
    escritos = generar_dashboard(RUTA_DB, [RUTA_REPORTES / "dashboard.html"], politica["institucion"].get("nombre", ""),
                                 politica["_catalogo"], conf.get("aviso", ""), conf.get("portal_url", ""))
    copia_vieja = rutas["dashboard"] / "Dashboard_CajaChica.html"
    if copia_vieja.exists():
        copia_vieja.unlink()
    url = conf.get("url") or ""
    acceso = rutas["dashboard"] / "Abrir_Dashboard_CajaChica.html"
    acceso.write_text(
        f'<!doctype html><meta charset="utf-8"><title>Dashboard de Caja Chica</title>'
        + (f'<meta http-equiv="refresh" content="0; url={url}"><p>Abriendo el dashboard… '
           f'Si no se abre, use este enlace: <a href="{url}">{url}</a></p>' if url else
           '<p>El dashboard aún no tiene enlace oficial. Consulte al administrador.</p>'),
        encoding="utf-8")
    return escritos + [acceso]


def _resumen(dias: int):
    desde = (date.today() - timedelta(days=dias)).isoformat()
    db = BaseDatos(RUTA_DB)
    q = db.consultar
    datos = {
        "desde": desde,
        "liquidaciones": q("SELECT caja, numero, custodio, fecha, total_facturas, n_facturas, n_rechazadas, "
                           "n_observadas, estado FROM liquidaciones WHERE fecha_proceso >= ? ORDER BY caja", (desde,)),
        "arqueos": q("SELECT caja, fecha, custodio, realizado_por, fondo, efectivo, pendientes_facturas, vales, "
                     "diferencia, estado FROM arqueos WHERE fecha_proceso >= ?", (desde,)),
        "hallazgos_alta_media": q(
            "SELECT h.severidad, h.caja, h.regla, h.detalle, h.monto, l.numero AS liquidacion, f.fila, f.proveedor, "
            "f.descripcion, f.fecha FROM hallazgos h LEFT JOIN facturas f ON f.id=h.factura_id "
            "LEFT JOIN liquidaciones l ON l.id=h.liquidacion_id WHERE h.fecha_registro >= ? AND h.severidad IN "
            "('ALTA','MEDIA') ORDER BY h.severidad, h.caja", (desde,)),
        "gasto_por_categoria": q("SELECT categoria, ROUND(SUM(total_crc)) total, COUNT(*) n FROM facturas f JOIN "
                                 "liquidaciones l ON l.id=f.liquidacion_id WHERE l.fecha_proceso >= ? "
                                 "GROUP BY categoria ORDER BY total DESC", (desde,)),
        "top_proveedores": q("SELECT proveedor, ROUND(SUM(total_crc)) total, COUNT(*) n FROM facturas f JOIN "
                             "liquidaciones l ON l.id=f.liquidacion_id WHERE l.fecha_proceso >= ? "
                             "GROUP BY proveedor ORDER BY total DESC LIMIT 10", (desde,)),
        "historico_semanal": q("SELECT strftime('%Y-%W', fecha) semana, caja, ROUND(SUM(total_crc)) total "
                               "FROM facturas GROUP BY semana, caja ORDER BY semana"),
    }
    db.cerrar()
    return datos


def main():
    comando = sys.argv[1] if len(sys.argv) > 1 else "procesar"
    politica = cargar_politica()
    rutas = carpetas(politica)
    if comando == "iniciar":
        if not RUTA_CATALOGO.exists() and not RUTA_CATALOGO.with_suffix(".csv").exists():
            print("Catálogo de cajas (complételo):", crear_catalogo(RUTA_CATALOGO))
        for p in crear_plantillas(rutas["plantillas"], politica):
            print("Plantilla:", p)
        print("Repositorio listo en:", rutas["entrada"].parent)
    elif comando == "demo":
        if not politica["_catalogo"]:
            crear_catalogo(RUTA_CATALOGO, CATALOGO_DEMO)
            politica = cargar_politica()
            print("Catálogo de demostración:", RUTA_CATALOGO)
        for p in crear_demo(rutas["entrada"], politica):
            print("Ejemplo:", p.name)
    elif comando == "procesar":
        bitacora = procesar(politica)
        bitacora["dashboard"] = [str(p) for p in _dashboard(politica, rutas)]
        print(json.dumps(bitacora, ensure_ascii=False, indent=2, default=str))
    elif comando == "proveedores":
        from cajachica.comprobantes import procesar_comprobantes
        db = BaseDatos(RUTA_DB)
        print(json.dumps(procesar_comprobantes(politica, db), ensure_ascii=False, indent=2, default=str))
        db.cerrar()
        _dashboard(politica, rutas)
    elif comando == "portal":
        from cajachica.portal import generar_portal
        print("Portal:", generar_portal(RUTA_REPORTES / "portal_proveedores.html", politica))
    elif comando == "importar-web":
        from cajachica.portal_remoto import importar
        db = BaseDatos(RUTA_DB)
        res = importar(politica, db)
        db.cerrar()
        _dashboard(politica, rutas)
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    elif comando == "importar-portal":
        from pathlib import Path
        from cajachica.comprobantes import procesar_comprobantes
        from cajachica.portal import importar_envios
        db = BaseDatos(RUTA_DB)
        hechos = {r["envio"] for r in db.consultar("SELECT envio FROM portal_importados")}
        res = importar_envios(Path(sys.argv[2]), politica, hechos)
        for x in res["importados"]:
            db.insertar("portal_importados", {"envio": x["envio"], "persona": x["persona"], "clave": x["clave"],
                                              "importado": x["importado"]})
        db.commit()
        res["cruce"] = procesar_comprobantes(politica, db)
        db.cerrar()
        _dashboard(politica, rutas)
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    elif comando.startswith("respaldo"):
        from pathlib import Path
        from cajachica import respaldo
        db = BaseDatos(RUTA_DB)
        if comando == "respaldo-pendiente":
            res = respaldo.pendientes(politica, db)
            ids = respaldo.cargar_ids()
            res["carpetas_por_crear"] = respaldo.carpetas_faltantes(res["carpetas_necesarias"], ids)
            res["carpetas_drive"] = ids
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif comando == "respaldo-registrar":
            subidos = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
            for x in subidos:
                respaldo.registrar(db, x["ruta"], x["hash"], x["drive_id"], x["carpeta"], x["nombre"])
            print(f"{len(subidos)} archivos registrados como respaldados.")
        elif comando == "respaldo-local":
            for p in respaldo.copiar_a_carpeta_local(politica, db, Path(sys.argv[2]).expanduser()):
                print("Copiado:", p)
        elif comando == "respaldo-bitacora":
            from cajachica.bitacora import exportar_csv
            for p in exportar_csv(Path(sys.argv[2])):
                print("Bitácora:", p)
        db.cerrar()
    elif comando == "dashboard":
        for p in _dashboard(politica, rutas):
            print("Dashboard:", p)
    elif comando == "informe":
        args = sys.argv[2:]
        if len(args) == 2:
            desde, hasta = date.fromisoformat(args[0]), date.fromisoformat(args[1])
        else:
            hasta = date.today()
            desde = hasta - timedelta(days=int(args[0]) if args else 7)
        nombre = f"Informe_Incumplimientos_{desde:%Y%m%d}_{hasta:%Y%m%d}.xlsx"
        for p in generar_informe(RUTA_DB, politica, desde, hasta, [RUTA_REPORTES / nombre, rutas["informes"] / nombre]):
            print("Informe:", p)
    elif comando == "resumen":
        dias = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print(json.dumps(_resumen(dias), ensure_ascii=False, indent=2, default=str))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
