"""Portal de proveedores externos (FastAPI). Se ejecuta con:
    uvicorn portal_web.app:app --host 0.0.0.0 --port $PORT
"""
import csv
import io
import re
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import false, func, insert, select, update
from starlette.middleware.sessions import SessionMiddleware

from . import config, db
from .almacen import almacen
from .seguridad import fallo, hash_password, limitar, token_csrf, validar_csrf, verificar_password
from .verificacion import EnvioInvalido, analizar, politica

BASE = Path(__file__).parent
app = FastAPI(title=config.NOMBRE_PORTAL, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, session_cookie="portal_sesion",
                   max_age=8 * 3600, same_site="lax", https_only=config.PRODUCCION)
app.mount("/estatico", StaticFiles(directory=BASE / "estatico"), name="estatico")
plantillas = Jinja2Templates(directory=BASE / "plantillas")

ESTADOS_ENVIO = {"RECIBIDO": "Recibido", "EN_REVISION": "En revisión", "APROBADO": "Aprobado",
                 "DEVUELTO": "Devuelto para corregir", "RECHAZADO": "Rechazado"}
TIPOS_MIME = {"pdf": "application/pdf", "factura": "application/xml", "respuesta": "application/xml"}


@app.on_event("startup")
def _inicio():
    db.iniciar()


@app.middleware("http")
async def cabeceras(request: Request, call_next):
    r = await call_next(request)
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Referrer-Policy"] = "same-origin"
    r.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
    if config.PRODUCCION:
        r.headers["Strict-Transport-Security"] = "max-age=31536000"
    return r


def ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0].strip()


def ver(request: Request, plantilla: str, **ctx):
    inst = politica()["institucion"]
    aviso = request.session.pop("aviso", None)
    return plantillas.TemplateResponse(request, plantilla, {
        "csrf": token_csrf(request), "aviso": aviso, "portal": config.NOMBRE_PORTAL, "institucion": inst["nombre"],
        "cedula_inst": inst["cedula_juridica"], "estados": ESTADOS_ENVIO, "es_admin": request.session.get("rol") == "admin",
        "modo_proveedor": request.session.get("modo") == "proveedor", "dashboard_url": config.DASHBOARD_URL, **ctx})


def avisar(request: Request, texto: str, tipo: str = "exito"):
    request.session["aviso"] = {"texto": texto, "tipo": tipo}


def proveedor_actual(request: Request) -> dict:
    pid = request.session.get("proveedor_id")
    p = db.uno(select(db.proveedores).where(db.proveedores.c.id == pid)) if pid else None
    if not p:
        destino = "/admin/vista-proveedor" if request.session.get("rol") == "admin" else "/ingresar"
        raise HTTPException(status_code=303, headers={"Location": destino})
    # El superadministrador solo puede actuar como su proveedor de prueba, nunca como uno real
    if request.session.get("rol") == "admin" and not p.get("es_prueba"):
        raise HTTPException(status_code=403, detail="Solo puede actuar como el proveedor de prueba.")
    return p


def admin_actual(request: Request) -> str:
    if request.session.get("rol") != "admin":
        raise HTTPException(status_code=303, headers={"Location": "/ingresar"})
    return request.session["admin"]


def api_autorizada(request: Request):
    import hmac
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not config.API_TOKEN or not hmac.compare_digest(token, config.API_TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido")


# ------------------------------------------------------------------ inicio, registro e ingreso

@app.get("/salud")
def salud():
    return {"ok": True, "almacen": config.ALMACEN}


@app.get("/")
def raiz(request: Request):
    if request.session.get("rol") == "admin":
        return RedirectResponse("/admin", 303)
    if request.session.get("proveedor_id"):
        return RedirectResponse("/proveedor", 303)
    return RedirectResponse("/ingresar", 303)


@app.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request):
    return ver(request, "registro.html", datos={})


@app.post("/registro")
def registro(request: Request, csrf: str = Form(""), cedula: str = Form(...), razon_social: str = Form(...),
             nombre_comercial: str = Form(""), correo: str = Form(...), telefono: str = Form(""),
             password: str = Form(...), password2: str = Form(...)):
    validar_csrf(request, csrf)
    datos = {"cedula": cedula, "razon_social": razon_social, "nombre_comercial": nombre_comercial, "correo": correo,
             "telefono": telefono}
    ced = re.sub(r"\D", "", cedula)
    correo = correo.strip().lower()
    error = ("La cédula debe tener entre 9 y 12 dígitos." if not 9 <= len(ced) <= 12 else
             "Indique la razón social." if not razon_social.strip() else
             "El correo no es válido." if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo) else
             "La contraseña debe tener al menos 10 caracteres." if len(password) < 10 else
             "Las contraseñas no coinciden." if password != password2 else None)
    if not error and db.uno(select(db.proveedores).where((db.proveedores.c.cedula == ced) | (db.proveedores.c.correo == correo))):
        error = "Ya existe un registro con esa cédula o ese correo. Ingrese con su contraseña."
    if error:
        return ver(request, "registro.html", datos=datos, error=error)
    r = db.ejecutar(insert(db.proveedores).values(
        cedula=ced, razon_social=razon_social.strip()[:200], nombre_comercial=nombre_comercial.strip()[:200],
        correo=correo, telefono=telefono.strip()[:40], password_hash=hash_password(password), estado="Pendiente",
        comentario="", creado=db.ahora()))
    request.session.clear()
    request.session["proveedor_id"] = r.inserted_primary_key[0]
    db.registrar(f"proveedor:{ced}", "registro", razon_social, ip(request))
    avisar(request, "Registro creado. Queda pendiente de aprobación por la Universidad; ya puede enviar facturas.")
    return RedirectResponse("/proveedor", 303)


@app.get("/ingresar", response_class=HTMLResponse)
def ingresar_form(request: Request):
    return ver(request, "ingresar.html")


@app.post("/ingresar")
def ingresar(request: Request, csrf: str = Form(""), usuario: str = Form(...), password: str = Form(...)):
    validar_csrf(request, csrf)
    usuario = usuario.strip().lower()
    limitar(f"ip:{ip(request)}", maximo=20)
    limitar(f"u:{usuario}")
    if config.ADMIN_EMAIL and usuario == config.ADMIN_EMAIL and config.ADMIN_PASSWORD:
        import hmac
        if hmac.compare_digest(password, config.ADMIN_PASSWORD):
            request.session.clear()
            request.session.update({"rol": "admin", "admin": usuario})
            db.registrar(f"admin:{usuario}", "ingreso", "", ip(request))
            return RedirectResponse("/admin", 303)
    ced = re.sub(r"\D", "", usuario)
    p = db.uno(select(db.proveedores).where((db.proveedores.c.correo == usuario) |
                                            ((db.proveedores.c.cedula == ced) if ced else false())))
    if p and verificar_password(password, p["password_hash"]):
        request.session.clear()
        request.session["proveedor_id"] = p["id"]
        db.registrar(f"proveedor:{p['cedula']}", "ingreso", "", ip(request))
        return RedirectResponse("/proveedor", 303)
    fallo(f"ip:{ip(request)}")
    fallo(f"u:{usuario}")
    db.registrar(f"desconocido:{usuario}", "ingreso_fallido", "", ip(request))
    return ver(request, "ingresar.html", error="Usuario o contraseña incorrectos.", usuario=usuario)


@app.post("/salir")
def salir(request: Request, csrf: str = Form("")):
    validar_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/ingresar", 303)


# ------------------------------------------------------------------ vista proveedor

def _envios_de(pid: int) -> list[dict]:
    return db.todos(select(db.envios).where(db.envios.c.proveedor_id == pid).order_by(db.envios.c.creado.desc()))


@app.get("/proveedor", response_class=HTMLResponse)
def vista_proveedor(request: Request, p: dict = Depends(proveedor_actual)):
    return ver(request, "proveedor.html", p=p, envios=_envios_de(p["id"]), solo_lectura=False)


async def _leer(archivo: UploadFile, maximo: int, nombre: str) -> bytes:
    contenido = await archivo.read(maximo + 1)
    if not contenido:
        raise EnvioInvalido(f"Falta el archivo «{nombre}».")
    if len(contenido) > maximo:
        raise EnvioInvalido(f"El archivo «{nombre}» supera el tamaño máximo ({maximo // 1024} KB).")
    return contenido


@app.post("/proveedor/enviar")
async def enviar(request: Request, csrf: str = Form(""), pdf: UploadFile = File(...), xml: UploadFile = File(...),
                 respuesta: UploadFile = File(...), p: dict = Depends(proveedor_actual)):
    validar_csrf(request, csrf)
    if p["estado"] == "Rechazado":
        avisar(request, "Su registro fue rechazado; no puede enviar facturas. Comuníquese con la Universidad.", "error")
        return RedirectResponse("/proveedor", 303)
    try:
        b_pdf = await _leer(pdf, int(config.MAX_PDF_MB * 1024 * 1024), "PDF de la factura")
        if not b_pdf.startswith(b"%PDF"):
            raise EnvioInvalido("El archivo de la casilla «PDF» no es un PDF.")
        b_xml = await _leer(xml, int(config.MAX_XML_KB * 1024), "XML de la factura")
        b_resp = await _leer(respuesta, int(config.MAX_XML_KB * 1024), "Respuesta de Hacienda")
        a = analizar(b_pdf, pdf.filename or "", b_xml, b_resp, p)
    except EnvioInvalido as e:
        avisar(request, str(e), "error")
        return RedirectResponse("/proveedor", 303)

    fac = a["factura"]
    previo = db.uno(select(db.envios).where(db.envios.c.clave == fac["clave"]))
    if previo and previo["estado"] != "DEVUELTO":
        avisar(request, f"La factura {fac['consecutivo']} ya fue enviada ({ESTADOS_ENVIO[previo['estado']]}).", "error")
        return RedirectResponse("/proveedor", 303)

    n = fac["consecutivo"] or fac["clave"][21:41]
    try:
        alm = almacen()
        archivos = {
            "pdf": alm.guardar(a["carpeta"], f"Factura_{n}.pdf", b_pdf, TIPOS_MIME["pdf"]),
            "factura": alm.guardar(a["carpeta"], f"Factura_{n}.xml", b_xml, TIPOS_MIME["factura"]),
            "respuesta": alm.guardar(a["carpeta"], f"Respuesta_Hacienda_{n}.xml", b_resp, TIPOS_MIME["respuesta"]),
        }
    except Exception as e:  # Drive caído, credenciales vencidas, etc.
        db.registrar(f"proveedor:{p['cedula']}", "error_almacen", str(e), ip(request))
        avisar(request, "No se pudieron guardar los archivos. Intente de nuevo en unos minutos.", "error")
        return RedirectResponse("/proveedor", 303)

    valores = dict(
        proveedor_id=p["id"], clave=fac["clave"], consecutivo=fac["consecutivo"], fecha_emision=str(fac["fecha"] or ""),
        emisor_cedula=fac["emisor_cedula"], emisor_nombre=fac["emisor_nombre"], receptor_cedula=fac["receptor_cedula"],
        total=fac["total"], impuesto=fac["impuesto"], moneda=fac["moneda"],
        hacienda={"1": "Aceptado", "2": "Aceptado parcialmente", "3": "Rechazado"}.get(a["respuesta"]["mensaje"], "Desconocido"),
        descripcion=fac["descripcion"], controles=a["controles"], cruce=a["cruce"], estado="RECIBIDO", comentario="",
        archivos=archivos, carpeta="/".join(a["carpeta"]), actualizado=db.ahora())
    if previo:
        db.ejecutar(update(db.envios).where(db.envios.c.id == previo["id"]).values(**valores))
    else:
        db.ejecutar(insert(db.envios).values(creado=db.ahora(), **valores))
    db.registrar(f"proveedor:{p['cedula']}", "envio", f"{n} · {a['cruce']}", ip(request))
    fallas = [c["control"] for c in a["controles"] if c["estado"] == "NO CUMPLE"]
    avisar(request, f"Factura {n} enviada." + (f" Atención: {len(fallas)} {'control no cumple' if len(fallas) == 1 else 'controles no cumplen'} ({', '.join(fallas)}); la Universidad podría devolverla."
                                              if fallas else " Todos los controles coinciden."), "aviso" if fallas else "exito")
    return RedirectResponse("/proveedor", 303)


# ------------------------------------------------------------------ vista proveedor del superadministrador

EJEMPLO = {"id": 0, "cedula": "3-101-000000", "razon_social": "Proveedor de ejemplo S.A.", "nombre_comercial": "",
           "correo": "facturacion@proveedor-ejemplo.cr", "telefono": "2222-0000", "estado": "Pendiente", "comentario": ""}


def _correo_prueba(admin: str) -> str:
    usuario, _, dominio = admin.partition("@")
    return f"{usuario}+proveedor-prueba@{dominio}"


@app.get("/admin/vista-proveedor", response_class=HTMLResponse)
def admin_vista_proveedor(request: Request, admin: str = Depends(admin_actual)):
    prueba = db.uno(select(db.proveedores).where(db.proveedores.c.correo == _correo_prueba(admin)))
    reales = db.todos(select(db.proveedores).where(db.proveedores.c.es_prueba.isnot(True))
                      .order_by(db.proveedores.c.razon_social))
    return ver(request, "vista_proveedor.html", prueba=prueba, reales=reales)


@app.get("/admin/vista-proveedor/previa", response_class=HTMLResponse)
def admin_vista_previa(request: Request, admin: str = Depends(admin_actual)):
    return ver(request, "proveedor.html", p=EJEMPLO, envios=[], solo_lectura=True, previa=True)


@app.post("/admin/proveedor-prueba")
def admin_proveedor_prueba(request: Request, csrf: str = Form(""), cedula: str = Form(...), razon_social: str = Form(...),
                           admin: str = Depends(admin_actual)):
    """Crea (o actualiza) el proveedor de prueba del superadministrador y entra al portal como él."""
    validar_csrf(request, csrf)
    import secrets
    ced = re.sub(r"\D", "", cedula)
    if not 9 <= len(ced) <= 12 or not razon_social.strip():
        avisar(request, "Indique una cédula de 9 a 12 dígitos y la razón social del proveedor de prueba.", "error")
        return RedirectResponse("/admin/vista-proveedor", 303)
    otro = db.uno(select(db.proveedores).where((db.proveedores.c.cedula == ced) & (db.proveedores.c.es_prueba.isnot(True))))
    if otro:
        avisar(request, "Esa cédula pertenece a un proveedor real. Use otra para las pruebas.", "error")
        return RedirectResponse("/admin/vista-proveedor", 303)
    correo = _correo_prueba(admin)
    previo = db.uno(select(db.proveedores).where(db.proveedores.c.correo == correo))
    if previo:
        db.ejecutar(update(db.proveedores).where(db.proveedores.c.id == previo["id"]).values(
            cedula=ced, razon_social=razon_social.strip()[:200]))
        pid = previo["id"]
    else:
        pid = db.ejecutar(insert(db.proveedores).values(
            cedula=ced, razon_social=razon_social.strip()[:200], nombre_comercial="", correo=correo, telefono="",
            password_hash="sin-ingreso-directo$" + secrets.token_hex(8), estado="Aprobado",
            comentario="Proveedor de prueba del superadministrador.", creado=db.ahora(), es_prueba=True)).inserted_primary_key[0]
    request.session["proveedor_id"] = pid
    request.session["modo"] = "proveedor"
    db.registrar(f"admin:{admin}", "modo_proveedor_prueba", f"{ced} {razon_social}", ip(request))
    return RedirectResponse("/proveedor", 303)


@app.post("/admin/volver")
def admin_volver(request: Request, csrf: str = Form(""), admin: str = Depends(admin_actual)):
    validar_csrf(request, csrf)
    request.session.pop("proveedor_id", None)
    request.session.pop("modo", None)
    return RedirectResponse("/admin", 303)


# ------------------------------------------------------------------ vista administrador

@app.get("/admin", response_class=HTMLResponse)
def vista_admin(request: Request, estado: str = "", admin: str = Depends(admin_actual)):
    request.session.pop("modo", None)
    request.session.pop("proveedor_id", None)
    provs = db.todos(select(db.proveedores).order_by(db.proveedores.c.creado.desc()))
    consulta = select(db.envios, db.proveedores.c.razon_social, db.proveedores.c.es_prueba).join(db.proveedores) \
        .order_by(db.envios.c.creado.desc())
    if estado:
        consulta = consulta.where(db.envios.c.estado == estado)
    envs = db.todos(consulta)
    kpis = {
        "proveedores": len(provs), "pendientes": sum(1 for x in provs if x["estado"] == "Pendiente"),
        "envios": db.uno(select(func.count().label("n")).select_from(db.envios))["n"],
        "por_decidir": db.uno(select(func.count().label("n")).select_from(db.envios).where(db.envios.c.estado.in_(["RECIBIDO", "EN_REVISION"])))["n"],
        "con_diferencias": db.uno(select(func.count().label("n")).select_from(db.envios).where(db.envios.c.cruce == "CON DIFERENCIAS"))["n"],
    }
    return ver(request, "admin.html", provs=provs, envios=envs, kpis=kpis, filtro=estado, almacen=config.ALMACEN)


@app.post("/admin/proveedor/{pid}/estado")
def admin_estado_proveedor(request: Request, pid: int, csrf: str = Form(""), estado: str = Form(...),
                           comentario: str = Form(""), admin: str = Depends(admin_actual)):
    validar_csrf(request, csrf)
    if estado not in ("Aprobado", "Rechazado", "Pendiente"):
        raise HTTPException(400)
    db.ejecutar(update(db.proveedores).where(db.proveedores.c.id == pid).values(
        estado=estado, comentario=comentario.strip()[:500], revisado=db.ahora()))
    db.registrar(f"admin:{admin}", "estado_proveedor", f"{pid} → {estado} · {comentario}", ip(request))
    # La verificación de sus facturas incluye el control "Proveedor registrado": se actualiza con la decisión
    from cajachica.comprobantes import estado_general
    for e in db.todos(select(db.envios).where(db.envios.c.proveedor_id == pid)):
        ctrls = [dict(c) for c in (e["controles"] or [])]
        for c in ctrls:
            if c["control"] == "Proveedor registrado":
                c["estado"] = "CUMPLE" if estado == "Aprobado" else "NO CUMPLE"
                c["detalle"] = f"Registro {estado.lower()}."
        db.ejecutar(update(db.envios).where(db.envios.c.id == e["id"]).values(
            controles=ctrls, cruce=estado_general(ctrls, vencido=True)))
    avisar(request, f"Proveedor marcado como {estado}.")
    return RedirectResponse("/admin#proveedores", 303)


@app.post("/admin/envio/{eid}/estado")
def admin_estado_envio(request: Request, eid: int, csrf: str = Form(""), estado: str = Form(...),
                       comentario: str = Form(""), admin: str = Depends(admin_actual)):
    validar_csrf(request, csrf)
    if estado not in ESTADOS_ENVIO:
        raise HTTPException(400)
    if estado in ("DEVUELTO", "RECHAZADO") and len(comentario.strip()) < 10:
        avisar(request, "Para devolver o rechazar escriba el motivo (lo verá el proveedor).", "error")
        return RedirectResponse("/admin#envios", 303)
    db.ejecutar(update(db.envios).where(db.envios.c.id == eid).values(
        estado=estado, comentario=comentario.strip()[:1000], actualizado=db.ahora()))
    db.registrar(f"admin:{admin}", "estado_envio", f"{eid} → {estado} · {comentario}", ip(request))
    avisar(request, f"Factura marcada como {ESTADOS_ENVIO[estado]}.")
    return RedirectResponse("/admin#envios", 303)


def _archivo(eid: int, tipo: str) -> Response:
    e = db.uno(select(db.envios).where(db.envios.c.id == eid))
    if not e or tipo not in (e["archivos"] or {}):
        raise HTTPException(404)
    a = e["archivos"][tipo]
    return Response(almacen().leer(a["id"]), media_type=TIPOS_MIME[tipo],
                    headers={"Content-Disposition": f'attachment; filename="{a["nombre"]}"'})


@app.get("/admin/envio/{eid}/archivo/{tipo}")
def admin_archivo(eid: int, tipo: str, admin: str = Depends(admin_actual)):
    return _archivo(eid, tipo)


@app.get("/admin/proveedor/{pid}", response_class=HTMLResponse)
def admin_como_proveedor(request: Request, pid: int, admin: str = Depends(admin_actual)):
    """El superadministrador ve exactamente lo que ve ese proveedor (sin poder enviar a su nombre)."""
    p = db.uno(select(db.proveedores).where(db.proveedores.c.id == pid))
    if not p:
        raise HTTPException(404)
    return ver(request, "proveedor.html", p=p, envios=_envios_de(pid), solo_lectura=True)


@app.get("/admin/bitacora", response_class=HTMLResponse)
def admin_bitacora(request: Request, admin: str = Depends(admin_actual)):
    filas = db.todos(select(db.bitacora).order_by(db.bitacora.c.ts.desc()).limit(500))
    return ver(request, "bitacora.html", filas=filas)


@app.get("/admin/bitacora.csv")
def admin_bitacora_csv(admin: str = Depends(admin_actual)):
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["Fecha y hora (UTC)", "Actor", "Acción", "Detalle", "IP"])
    for f in db.todos(select(db.bitacora).order_by(db.bitacora.c.ts)):
        w.writerow([f["ts"], f["actor"], f["accion"], f["detalle"], f["ip"]])
    return Response("﻿" + salida.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="Bitacora_portal_proveedores.csv"'})


# ------------------------------------------------------------------ dashboard de caja chica (administradores)

ROLES = ["Revisor de liquidaciones", "Validador de evidencia", "Jefatura / aprobador", "Auditoría interna", "Consulta"]
MOTIVOS = ["Revisión semanal de liquidaciones", "Validación de evidencia de hallazgos",
           "Confirmar que la información está al día", "Seguimiento de hallazgos abiertos", "Consulta general"]
RESULTADOS = {"CONFIRMADO": "Incumplimiento confirmado", "JUSTIFICADO": "Justificado: se acepta",
              "INFO": "Requiere más información", "FALSO": "Falso positivo"}
VIGENCIA = {"AL_DIA": "Al día", "DESACTUALIZADA": "Faltan entregas recientes", "INCONSISTENTE": "Datos inconsistentes"}


def _ultimo_tablero() -> dict | None:
    return db.uno(select(db.tablero).order_by(db.tablero.c.id.desc()).limit(1))


def _csrf_json(request: Request):
    validar_csrf(request, request.headers.get("x-csrf-token", ""))


@app.get("/admin/tablero", response_class=HTMLResponse)
def tablero(request: Request, admin: str = Depends(admin_actual)):
    request.session.pop("modo", None)
    request.session.pop("proveedor_id", None)
    t = _ultimo_tablero()
    if not request.session.get("revision"):
        return ver(request, "tablero_registro.html", roles=ROLES, motivos=MOTIVOS, corte=t["generado"] if t else "")
    return ver(request, "tablero.html", hay_datos=bool(t), revision=request.session["revision"])


@app.post("/admin/tablero/registro")
def tablero_registro(request: Request, csrf: str = Form(""), rol: str = Form(...), motivo: str = Form(...),
                     alcance: str = Form(""), declaracion: str = Form(""), admin: str = Depends(admin_actual)):
    validar_csrf(request, csrf)
    if rol not in ROLES or motivo not in MOTIVOS or declaracion != "si":
        avisar(request, "Elija rol y motivo y confirme la declaración para ingresar.", "error")
        return RedirectResponse("/admin/tablero", 303)
    t = _ultimo_tablero()
    request.session["revision"] = {"rol": rol, "motivo": motivo, "alcance": alcance.strip()[:200],
                                   "corte": t["generado"] if t else "", "ts": db.ahora().isoformat()}
    db.registrar(f"admin:{admin}", "ingreso_dashboard", f"{rol} · {motivo}" + (f" · {alcance.strip()[:200]}" if alcance.strip() else "")
                 + (f" · corte {t['generado']}" if t else ""), ip(request))
    return RedirectResponse("/admin/tablero", 303)


@app.get("/admin/tablero/datos.json")
def tablero_datos(request: Request, admin: str = Depends(admin_actual)):
    if not request.session.get("revision"):
        raise HTTPException(403, "Registre su revisión primero.")
    t = _ultimo_tablero()
    vals = db.todos(select(db.validaciones).order_by(db.validaciones.c.ts.desc()))
    vigs = db.todos(select(db.vigencias).order_by(db.vigencias.c.ts.desc()).limit(20))
    iso = lambda filas: [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in f.items()} for f in filas]
    return JSONResponse({"datos": t["datos"] if t else None, "recibido": t["recibido"].isoformat() if t else None,
                         "validaciones": iso(vals), "vigencias": iso(vigs), "resultados": RESULTADOS, "vigencia": VIGENCIA,
                         "revision": request.session["revision"]})


@app.post("/admin/tablero/validar")
async def tablero_validar(request: Request, admin: str = Depends(admin_actual)):
    _csrf_json(request)
    rev = request.session.get("revision") or {}
    c = await request.json()
    if c.get("resultado") not in RESULTADOS or len(str(c.get("comentario", "")).strip()) < 10 or not c.get("clave"):
        raise HTTPException(400, "Indique el resultado y describa la evidencia revisada (al menos 10 caracteres).")
    db.ejecutar(insert(db.validaciones).values(
        ts=db.ahora(), actor=admin, rol=rev.get("rol", ""), clave=str(c["clave"])[:40], resultado=c["resultado"],
        comentario=str(c["comentario"]).strip()[:1000], corte=rev.get("corte", ""), caja=str(c.get("caja", ""))[:40],
        regla=str(c.get("regla", ""))[:60], liquidacion=str(c.get("liquidacion", ""))[:60],
        fila=c.get("fila") if isinstance(c.get("fila"), int) else None))
    db.registrar(f"admin:{admin}", "validacion", f"{c.get('caja')} {c.get('liquidacion', '')} fila {c.get('fila', '')} · "
                 f"{c.get('regla')} → {RESULTADOS[c['resultado']]} · {str(c['comentario'])[:300]}", ip(request))
    return {"ok": True}


@app.post("/admin/tablero/vigencia")
async def tablero_vigencia(request: Request, admin: str = Depends(admin_actual)):
    _csrf_json(request)
    rev = request.session.get("revision") or {}
    c = await request.json()
    if c.get("resultado") not in VIGENCIA or (c["resultado"] != "AL_DIA" and len(str(c.get("comentario", "")).strip()) < 10):
        raise HTTPException(400, "Elija el resultado y, si no está al día, explique qué falta.")
    db.ejecutar(insert(db.vigencias).values(ts=db.ahora(), actor=admin, rol=rev.get("rol", ""), resultado=c["resultado"],
                                            comentario=str(c.get("comentario", "")).strip()[:1000], corte=rev.get("corte", "")))
    db.registrar(f"admin:{admin}", "vigencia", f"{VIGENCIA[c['resultado']]} · {str(c.get('comentario', ''))[:300]}", ip(request))
    return {"ok": True}


# ------------------------------------------------------------------ API para el agente (Bearer API_TOKEN)

@app.post("/api/tablero", dependencies=[Depends(api_autorizada)])
async def api_tablero(request: Request):
    """El agente publica aquí los datos del dashboard después de cada procesamiento."""
    datos = await request.json()
    if not isinstance(datos, dict) or "hallazgos" not in datos or "facturas" not in datos:
        raise HTTPException(400, "Formato de datos no reconocido.")
    db.ejecutar(insert(db.tablero).values(recibido=db.ahora(), generado=str(datos.get("generado", ""))[:40], datos=datos))
    viejos = db.todos(select(db.tablero.c.id).order_by(db.tablero.c.id.desc()).offset(10))
    if viejos:
        from sqlalchemy import delete
        db.ejecutar(delete(db.tablero).where(db.tablero.c.id.in_([v["id"] for v in viejos])))
    db.registrar("agente", "publicacion_dashboard", f"corte {datos.get('generado')} · {len(datos['facturas'])} facturas · "
                 f"{len(datos['hallazgos'])} hallazgos")
    return {"ok": True}


@app.get("/api/validaciones", dependencies=[Depends(api_autorizada)])
def api_validaciones():
    iso = lambda filas: [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in f.items()} for f in filas]
    return JSONResponse({"validaciones": iso(db.todos(select(db.validaciones))), "vigencias": iso(db.todos(select(db.vigencias)))})


@app.get("/api/envios", dependencies=[Depends(api_autorizada)])
def api_envios(estado: str = ""):
    consulta = select(db.envios, db.proveedores.c.razon_social, db.proveedores.c.estado.label("estado_proveedor")).join(db.proveedores) \
        .where(db.proveedores.c.es_prueba.isnot(True))   # el agente nunca recibe datos de prueba
    if estado:
        consulta = consulta.where(db.envios.c.estado == estado)
    return JSONResponse([{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in e.items()} for e in db.todos(consulta)])


@app.get("/api/proveedores", dependencies=[Depends(api_autorizada)])
def api_proveedores():
    return JSONResponse([{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in p.items() if k != "password_hash"}
                         for p in db.todos(select(db.proveedores).where(db.proveedores.c.es_prueba.isnot(True)))])


@app.get("/api/envios/{eid}/archivo/{tipo}", dependencies=[Depends(api_autorizada)])
def api_archivo(eid: int, tipo: str):
    return _archivo(eid, tipo)


@app.post("/api/envios/{eid}/estado", dependencies=[Depends(api_autorizada)])
async def api_estado(eid: int, request: Request):
    cuerpo = await request.json()
    if cuerpo.get("estado") not in ESTADOS_ENVIO:
        raise HTTPException(400, "Estado inválido")
    db.ejecutar(update(db.envios).where(db.envios.c.id == eid).values(
        estado=cuerpo["estado"], comentario=str(cuerpo.get("comentario", ""))[:1000], actualizado=db.ahora()))
    db.registrar("agente", "estado_envio", f"{eid} → {cuerpo['estado']}")
    return {"ok": True}
