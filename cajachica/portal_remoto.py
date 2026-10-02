"""Trae al agente las facturas que los proveedores cargaron en el portal web (Railway).

Usa la API del portal con el token de `PORTAL_API_TOKEN` (el mismo valor que `API_TOKEN` en Railway) y la
dirección de `PORTAL_WEB_URL` (o `dashboard.portal_web_url` en politica.yaml).
"""
import json
import os
import urllib.request
from datetime import date

from .comprobantes import carpetas_proveedores, cargar_proveedores, guardar_proveedores, procesar_comprobantes


def _api(base: str, token: str, ruta: str, metodo: str = "GET", cuerpo: dict | None = None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(base.rstrip("/") + ruta, data=datos, method=metodo,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        contenido = r.read()
        return json.loads(contenido) if r.headers.get_content_type() == "application/json" else contenido


def importar(politica: dict, db) -> dict:
    base = os.environ.get("PORTAL_WEB_URL") or (politica.get("dashboard") or {}).get("portal_web_url", "")
    token = os.environ.get("PORTAL_API_TOKEN", "")
    if not base or not token:
        raise SystemExit("Defina PORTAL_WEB_URL y PORTAL_API_TOKEN (el API_TOKEN configurado en Railway).")
    rutas = carpetas_proveedores(politica)
    hechos = {r["envio"] for r in db.consultar("SELECT envio FROM portal_importados")}
    resultado = {"importados": [], "proveedores_actualizados": 0}

    # Registro de proveedores: el estado que decide el administrador en el portal manda
    registro = cargar_proveedores()
    for p in _api(base, token, "/api/proveedores"):
        previo = registro.get(p["cedula"], {})
        registro[p["cedula"]] = {**previo, "cedula": p["cedula"], "razon_social": p["razon_social"],
                                 "nombre_comercial": p.get("nombre_comercial", ""), "correo": p["correo"],
                                 "telefono": p.get("telefono", ""), "estado": p["estado"],
                                 "fecha_registro": (p.get("creado") or "")[:10] or date.today().isoformat(),
                                 "observaciones": "Portal web" + (f": {p['comentario']}" if p.get("comentario") else "")}
        resultado["proveedores_actualizados"] += 1
    guardar_proveedores(registro)

    for e in _api(base, token, "/api/envios?estado=RECIBIDO"):
        clave = f"web-{e['id']}"
        if clave in hechos:
            continue
        n = e["consecutivo"] or e["clave"][21:41]
        destinos = {"pdf": rutas["pdf"] / f"Factura_{n}.pdf", "factura": rutas["xml"] / f"Factura_{n}.xml",
                    "respuesta": rutas["respuesta"] / f"Respuesta_Hacienda_{n}.xml"}
        for tipo, destino in destinos.items():
            destino.write_bytes(_api(base, token, f"/api/envios/{e['id']}/archivo/{tipo}"))
        _api(base, token, f"/api/envios/{e['id']}/estado", "POST",
             {"estado": "EN_REVISION", "comentario": "En revisión por la Universidad."})
        db.insertar("portal_importados", {"envio": clave, "persona": e["emisor_cedula"], "clave": e["clave"],
                                          "importado": date.today().isoformat()})
        resultado["importados"].append({"id": e["id"], "proveedor": e.get("razon_social"), "factura": n})
    db.commit()
    resultado["cruce"] = procesar_comprobantes(politica, db)
    return resultado
