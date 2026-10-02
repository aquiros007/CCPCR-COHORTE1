"""Portal de proveedores (página aparte del dashboard: no lleva ningún dato interno de la Universidad).

Vista proveedor: registro y envío de cada factura (PDF + XML + respuesta de Hacienda) con verificación inmediata.
Vista administrador (editores y dueño): aprobar registros y ver/descargar lo recibido. El superadministrador
puede alternar entre ambas.

Base de datos de la página:
  proveedores/<persona>                      registro del proveedor (lo escribe él)
  estado_proveedores/<persona>               Aprobado / Rechazado (lo escribe el administrador)
  envios/<persona>/facturas/<envio>          XML, respuesta, controles y metadatos del PDF
  envios/<persona>/pdf/<envio>-<n>           PDF en base64, en partes de 200 000 caracteres
  estado_envios/<persona>                    {items: {<envio>: {estado, comentario, ts}}} (lo escribe el administrador)
"""
import base64
import json
from datetime import datetime
from pathlib import Path

from .util import solo_digitos

REGLAS_PORTAL = [
    {"path": "", "read": "admin", "write": "admin"},
    {"path": "proveedores", "read": "admin", "write": "admin"},
    {"path": "proveedores/{self}", "read": "interact", "write": "interact"},
    {"path": "envios", "read": "admin", "write": "admin"},
    {"path": "envios/{self}", "read": "interact", "write": "interact"},
    {"path": "estado_proveedores", "read": "admin", "write": "admin"},
    {"path": "estado_proveedores/{self}", "read": "interact", "write": "admin"},
    {"path": "estado_envios", "read": "admin", "write": "admin"},
    {"path": "estado_envios/{self}", "read": "interact", "write": "admin"},
]


def generar_portal(destino: Path, politica: dict) -> Path:
    inst = politica["institucion"]
    conf = {
        "institucion": inst.get("nombre", ""),
        "cedula": solo_digitos(inst.get("cedula_juridica")),
        "cedula_texto": inst.get("cedula_juridica", ""),
        "tiposAceptados": [str(t).zfill(2) for t in politica["comprobantes"].get("tipos_documento_aceptados", ["01"])],
        "tolerancia": float((politica.get("proveedores") or {}).get("tolerancia_monto", 1)),
        "dashboard": (politica.get("dashboard") or {}).get("url", ""),
        "aviso": (politica.get("dashboard") or {}).get("aviso", ""),
    }
    html = PLANTILLA.replace("__CONF__", json.dumps(conf, ensure_ascii=False).replace("</", "<\\/"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    return destino


# ------------------------------------------------------------------ importación (la hace Claude con ArtifactData)

def _datos(ruta: Path) -> dict:
    d = json.loads(ruta.read_text(encoding="utf-8"))
    return d.get("data") if isinstance(d.get("data"), dict) else d


def importar_envios(carpeta_exportada: Path, politica: dict, ya_importados: set) -> dict:
    """Reconstruye en 07_Proveedores los envíos exportados del portal.

    `carpeta_exportada` es el `out_dir` de ArtifactData: <out>/envios/<persona>/facturas/<envio>.json y
    <out>/envios/<persona>/pdf/<envio>-<n>.json. Devuelve lo importado para marcarlo "En revisión".
    """
    from .comprobantes import carpetas_proveedores
    rutas = carpetas_proveedores(politica)
    resultado = {"importados": [], "omitidos": []}
    for ficha in sorted((carpeta_exportada / "envios").glob("*/facturas/*.json")):
        persona, envio = ficha.parent.parent.name, ficha.stem
        if envio in ya_importados:
            resultado["omitidos"].append(envio)
            continue
        d = _datos(ficha)
        nombre = f"{(d.get('consecutivo') or envio)}_{envio[:8]}"
        (rutas["xml"] / f"{nombre}.xml").write_text(d.get("xml_factura", ""), encoding="utf-8")
        (rutas["respuesta"] / f"Respuesta_{nombre}.xml").write_text(d.get("xml_respuesta", ""), encoding="utf-8")
        partes = sorted(ficha.parent.parent.glob(f"pdf/{envio}-*.json"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
        if partes and len(partes) == int(d.get("pdf_partes", len(partes))):
            b64 = "".join(_datos(p)["data"] for p in partes)
            (rutas["pdf"] / f"{nombre}.pdf").write_bytes(base64.b64decode(b64))
        resultado["importados"].append({"persona": persona, "envio": envio, "clave": d.get("clave", ""),
                                        "pdf": bool(partes), "importado": datetime.now().isoformat(timespec="seconds")})
    return resultado


PLANTILLA = r"""<title>Portal de Proveedores</title>
<style>
:root {
  color-scheme: light;
  --surface-0: #f4f4f2; --surface-1: #fcfcfb; --border: #e3e2de; --grid: #ecebe7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #7a7974;
  --series-1: #2a78d6; --accent: #1f3a5f;
  --good: #0ca30c; --warning: #fab219; --critical: #d03b3b;
  --good-bg: #e3f4e3; --warning-bg: #fdf1d6; --critical-bg: #f9e0e0; --neutral-bg: #ecebe7;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-0: #121211; --surface-1: #1a1a19; --border: #2e2e2c; --grid: #262624;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8f8e86;
    --series-1: #3987e5; --accent: #9ec5f4;
    --good-bg: #16301a; --warning-bg: #3a2f12; --critical-bg: #3d1a1a; --neutral-bg: #2a2a28;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0: #121211; --surface-1: #1a1a19; --border: #2e2e2c; --grid: #262624;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8f8e86;
  --series-1: #3987e5; --accent: #9ec5f4;
  --good-bg: #16301a; --warning-bg: #3a2f12; --critical-bg: #3d1a1a; --neutral-bg: #2a2a28;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
.envoltura { max-width: 1100px; margin: 0 auto; padding-inline: 24px; padding-block: 20px 48px; display: grid; gap: 16px; }
header { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 22px; text-wrap: balance; } h2 { font-size: 15px; margin: 0 0 10px; }
.sub { color: var(--text-secondary); font-size: 13px; }
.aviso { display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px; background: var(--warning-bg); font-size: 12px; font-weight: 600; }
.selector { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--surface-1); }
.selector button { font: inherit; font-size: 13px; font-weight: 600; padding: 7px 14px; border: 0; background: none; color: var(--text-secondary); cursor: pointer; }
.selector button[aria-pressed="true"] { background: var(--accent); color: var(--surface-1); }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; min-width: 0; }
.fila2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(380px, 100%), 1fr)); gap: 16px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.kpi { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.kpi .v { font-size: 24px; font-weight: 650; font-variant-numeric: tabular-nums; }
.kpi .l { font-size: 12px; color: var(--text-secondary); }
form.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: 12px; }
.campo { display: grid; gap: 5px; font-size: 13px; font-weight: 600; }
.ayuda { font-weight: 400; color: var(--text-muted); font-size: 12px; }
input, select, textarea { font: inherit; padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-1); color: var(--text-primary); width: 100%; }
textarea { min-height: 64px; resize: vertical; }
button.btn { font: inherit; font-weight: 600; padding: 8px 14px; border-radius: 8px; border: 1px solid var(--accent); background: var(--accent); color: var(--surface-1); cursor: pointer; }
button.btn.sec { background: var(--surface-1); color: var(--text-primary); border-color: var(--border); }
button.btn:disabled { opacity: .5; cursor: default; }
.btn-link { font: inherit; font-size: 12px; font-weight: 600; color: var(--series-1); background: none; border: 0; padding: 2px 0; cursor: pointer; }
button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 2px solid var(--series-1); outline-offset: 2px; }
.acciones { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.carga { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: 12px; }
.ranura { border: 1.5px dashed var(--border); border-radius: 10px; padding: 14px; display: grid; gap: 6px; background: var(--surface-0); }
.ranura.lleno { border-style: solid; border-color: var(--series-1); }
.ranura b { font-size: 13px; }
.ranura .nombre { font-size: 12px; color: var(--text-secondary); word-break: break-all; }
.controles { margin: 6px 0 0; padding: 0; list-style: none; display: grid; gap: 3px; font-size: 13px; }
.controles li { display: flex; gap: 8px; align-items: baseline; }
.marca { font-weight: 700; width: 14px; flex: none; text-align: center; }
.marca.ok { color: var(--good); } .marca.no { color: var(--critical); } .marca.nv { color: var(--warning); }
.pill { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap; background: var(--neutral-bg); }
.pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--text-muted); }
.pill.ok { background: var(--good-bg); } .pill.ok::before { background: var(--good); }
.pill.no { background: var(--critical-bg); } .pill.no::before { background: var(--critical); }
.pill.pend { background: var(--warning-bg); } .pill.pend::before { background: var(--warning); }
.tabla { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; color: var(--text-secondary); font-weight: 600; border-bottom: 1px solid var(--border); padding: 6px 8px; white-space: nowrap; }
td { border-bottom: 1px solid var(--grid); padding: 7px 8px; vertical-align: top; }
td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
details summary { cursor: pointer; color: var(--series-1); font-size: 12px; font-weight: 600; }
.vacio { color: var(--text-muted); padding: 18px 0; text-align: center; }
.mensaje { font-size: 13px; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface-0); }
.mensaje.error { border-color: var(--critical); color: var(--critical); }
.mensaje.exito { border-color: var(--good); }
.datos { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; font-size: 13px; margin: 0; }
.datos dt { color: var(--text-secondary); } .datos dd { margin: 0; }
@media (max-width: 640px) { .envoltura { padding-inline: 16px; } }
</style>

<div class="envoltura">
  <header>
    <div>
      <h1>Portal de Proveedores</h1>
      <div class="sub" id="subtitulo"></div>
    </div>
    <div class="acciones">
      <div class="selector" id="selector" hidden role="group" aria-label="Vista">
        <button type="button" data-vista="proveedor" aria-pressed="true">Vista proveedor</button>
        <button type="button" data-vista="admin" aria-pressed="false">Vista administrador</button>
      </div>
    </div>
  </header>

  <div class="mensaje" id="estadoPagina">Verificando su identidad…</div>

  <!-- ===================== VISTA PROVEEDOR ===================== -->
  <section id="vistaProveedor" hidden style="display:grid;gap:16px">
    <div class="fila2">
      <div class="card">
        <h2>1. Registro como proveedor</h2>
        <div id="registroResumen"></div>
        <form class="grid" id="formRegistro">
          <label class="campo" for="pCedula">Cédula física o jurídica<input id="pCedula" required inputmode="numeric" placeholder="3-101-123456"></label>
          <label class="campo" for="pRazon">Razón social<input id="pRazon" required maxlength="160"></label>
          <label class="campo" for="pComercial">Nombre comercial <span class="ayuda">Opcional</span><input id="pComercial" maxlength="160"></label>
          <label class="campo" for="pCorreo">Correo para notificaciones<input id="pCorreo" type="email" required maxlength="160"></label>
          <label class="campo" for="pTelefono">Teléfono<input id="pTelefono" maxlength="40"></label>
          <div class="acciones" style="align-self:end"><button class="btn" type="submit" id="btnRegistro">Guardar registro</button></div>
        </form>
        <div class="mensaje" id="msgRegistro" hidden></div>
      </div>
      <div class="card">
        <h2>Antes de enviar</h2>
        <ul class="controles">
          <li><span class="marca ok">1</span><span>La factura debe estar a nombre de <b class="inst"></b>, cédula jurídica <b class="ced"></b>.</span></li>
          <li><span class="marca ok">2</span><span>Suba los tres archivos de la misma factura: el PDF, el XML de la factura y el XML de respuesta de Hacienda.</span></li>
          <li><span class="marca ok">3</span><span>El portal revisa al instante que los tres coincidan. La Universidad hace la revisión final y le informa el resultado aquí.</span></li>
          <li><span class="marca ok">4</span><span>No se aceptan tiquetes electrónicos.</span></li>
        </ul>
      </div>
    </div>

    <div class="card" id="cardEnvio">
      <h2>2. Enviar una factura</h2>
      <div class="carga">
        <label class="ranura" id="rPdf" for="fPdf"><b>PDF de la factura</b><span class="nombre">Ningún archivo</span><input type="file" id="fPdf" accept="application/pdf,.pdf"></label>
        <label class="ranura" id="rXml" for="fXml"><b>XML de la factura electrónica</b><span class="nombre">Ningún archivo</span><input type="file" id="fXml" accept=".xml,text/xml,application/xml"></label>
        <label class="ranura" id="rResp" for="fResp"><b>XML de respuesta de Hacienda</b><span class="nombre">Ningún archivo</span><input type="file" id="fResp" accept=".xml,text/xml,application/xml"></label>
      </div>
      <div id="verificacion" style="margin-top:12px"></div>
      <div class="acciones" style="margin-top:12px">
        <button class="btn" type="button" id="btnEnviar" disabled>Enviar a la Universidad</button>
        <button class="btn sec" type="button" id="btnLimpiar">Limpiar</button>
        <span class="sub" id="ayudaEnvio">Registre sus datos y cargue los tres archivos.</span>
      </div>
      <div class="mensaje" id="msgEnvio" hidden style="margin-top:10px"></div>
    </div>

    <div class="card">
      <h2>3. Mis envíos</h2>
      <div class="tabla" id="tMisEnvios"></div>
    </div>
  </section>

  <!-- ===================== VISTA ADMINISTRADOR ===================== -->
  <section id="vistaAdmin" hidden style="display:grid;gap:16px">
    <div class="kpis" id="kpisAdmin"></div>
    <div class="card">
      <div class="acciones" style="justify-content:space-between">
        <h2 style="margin:0">Registro de proveedores</h2>
        <div class="acciones"><a class="btn-link" id="linkDashboard" target="_blank" rel="noopener" hidden>Abrir el dashboard de revisión</a>
          <button class="btn sec" type="button" id="btnActualizar">Actualizar</button></div>
      </div>
      <div class="tabla" id="tProveedores" style="margin-top:10px"></div>
    </div>
    <div class="card">
      <h2>Facturas recibidas</h2>
      <p class="sub" style="margin:0 0 10px">Verificación preliminar hecha en el navegador del proveedor. La revisión formal y la aprobación se hacen en el dashboard después de que Claude importa los envíos.</p>
      <div class="tabla" id="tEnvios"></div>
    </div>
  </section>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js"></script>
<script>
const CONF = __CONF__;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = n => n == null || isNaN(n) ? "—" : "₡" + Number(n).toLocaleString("es-CR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fh = s => { try { return new Date(s).toLocaleString("es-CR", { dateStyle: "short", timeStyle: "short" }); } catch (e) { return s; } };
const digitos = s => String(s ?? "").replace(/\D/g, "");
const S = { U: null, DB: null, me: null, admin: false, vista: "proveedor", registro: null, estadoReg: null,
            envios: [], estados: {}, archivos: { pdf: null, xml: null, resp: null }, analisis: null, downloads: null,
            adminProv: [], adminEnvios: [], adminEstadoProv: {}, adminEstadoEnv: {} };
const ESTADOS_ENVIO = { RECIBIDO: ["Recibido", "pend"], EN_REVISION: ["En revisión", "pend"], APROBADO: ["Aprobado", "ok"],
                        DEVUELTO: ["Devuelto para corregir", "pend"], RECHAZADO: ["Rechazado", "no"] };
const pill = (texto, clase) => `<span class="pill ${clase}">${esc(texto)}</span>`;
const marca = e => e === "ok" ? '<span class="marca ok" aria-label="Cumple">✓</span>' : e === "no"
  ? '<span class="marca no" aria-label="No cumple">✗</span>' : '<span class="marca nv" aria-label="Pendiente">?</span>';

document.querySelectorAll(".inst").forEach(e => e.textContent = CONF.institucion);
document.querySelectorAll(".ced").forEach(e => e.textContent = CONF.cedula_texto);
$("#subtitulo").innerHTML = `${esc(CONF.institucion)} · comprobantes electrónicos para caja chica${CONF.aviso ? ` <span class="aviso">${esc(CONF.aviso)}</span>` : ""}`;
if (CONF.dashboard) { $("#linkDashboard").href = CONF.dashboard; $("#linkDashboard").hidden = false; }

function mensaje(sel, texto, tipo = "") { const el = $(sel); el.textContent = texto; el.className = "mensaje " + tipo; el.hidden = !texto; }

// ------------------------------------------------------------ lectura de XML y PDF en el navegador
const nodo = (doc, ruta) => ruta.split("/").reduce((n, t) => n && [...n.children].find(c => c.localName === t), doc.documentElement);
const txt = (doc, ruta) => (nodo(doc, ruta)?.textContent || "").trim();
function leerXml(texto) {
  const doc = new DOMParser().parseFromString(texto, "application/xml");
  if (doc.querySelector("parsererror")) return { tipo: "ilegible" };
  const raiz = doc.documentElement.localName;
  if (raiz === "MensajeHacienda") return { tipo: "respuesta", clave: digitos(txt(doc, "Clave")),
    emisor: digitos(txt(doc, "NumeroCedulaEmisor")), receptor: digitos(txt(doc, "NumeroCedulaReceptor")),
    mensaje: txt(doc, "Mensaje"), detalle: txt(doc, "DetalleMensaje"),
    impuesto: parseFloat(txt(doc, "MontoTotalImpuesto")) || 0, total: parseFloat(txt(doc, "TotalFactura")) };
  if (raiz === "MensajeReceptor") return { tipo: "mensaje_receptor" };
  if (/Electronica|Electronico/.test(raiz)) return { tipo: "factura", documento: raiz, clave: digitos(txt(doc, "Clave")),
    consecutivo: digitos(txt(doc, "NumeroConsecutivo")), fecha: txt(doc, "FechaEmision").slice(0, 10),
    emisorNombre: txt(doc, "Emisor/Nombre"), emisor: digitos(txt(doc, "Emisor/Identificacion/Numero")),
    receptor: digitos(txt(doc, "Receptor/Identificacion/Numero")),
    impuesto: parseFloat(txt(doc, "ResumenFactura/TotalImpuesto")) || 0, total: parseFloat(txt(doc, "ResumenFactura/TotalComprobante")),
    firmado: [...doc.getElementsByTagName("*")].some(e => e.localName === "Signature") };
  return { tipo: "otro", raiz };
}
async function textoPdf(buffer) {
  if (!window.pdfjsLib) return null;
  try {
    const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(buffer.slice(0)) }).promise;
    let t = "";
    for (let i = 1; i <= Math.min(pdf.numPages, 5); i++) {
      const c = await (await pdf.getPage(i)).getTextContent();
      t += c.items.map(x => x.str).join(" ") + "\n";
    }
    return t;
  } catch (e) { return null; }
}
const montosEn = t => (t.match(/\d[\d.,\s]*\d/g) || []).map(m => { let s = m.replace(/\s/g, "");
  if (s.includes(",") && s.includes(".")) s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  else if (s.includes(",")) s = /,\d{1,2}$/.test(s) ? s.replace(",", ".") : s.replace(/,/g, "");
  return parseFloat(s); }).filter(n => !isNaN(n));

function verificar() {
  const { pdf, xml, resp } = S.archivos, f = xml?.datos, r = resp?.datos, tol = CONF.tolerancia, c = [];
  const add = (control, estado, detalle = "") => c.push({ control, estado, detalle });
  if (xml && f?.tipo !== "factura") add("XML de la factura válido", "no", f?.tipo === "respuesta" ? "Este archivo es la respuesta de Hacienda: cárguelo en la tercera casilla." : "No es el XML de una factura electrónica.");
  if (resp && r?.tipo !== "respuesta") add("XML de respuesta de Hacienda válido", "no", r?.tipo === "mensaje_receptor" ? "Es la aceptación del receptor, no la respuesta de Hacienda." : r?.tipo === "factura" ? "Este archivo es la factura: cárguelo en la segunda casilla." : "No es la respuesta de Hacienda (MensajeHacienda).");
  const F = f?.tipo === "factura" ? f : null, R = r?.tipo === "respuesta" ? r : null;
  if (F) {
    const tipoDoc = F.clave.slice(29, 31);
    add("Factura electrónica (no tiquete)", CONF.tiposAceptados.includes(tipoDoc) ? "ok" : "no", F.documento);
    add(`A nombre de ${CONF.institucion}`, F.receptor === CONF.cedula ? "ok" : "no", `Cédula del receptor: ${F.receptor || "(vacía)"}`);
    add("XML con firma digital", F.firmado ? "ok" : "no");
    if (S.registro) add("La factura es de su cédula registrada", F.emisor === digitos(S.registro.cedula) ? "ok" : "no", `Emisor ${F.emisor}`);
  }
  if (R) add("Hacienda aceptó el comprobante", R.mensaje === "1" ? "ok" : "no", R.mensaje === "1" ? "Aceptado" : (R.mensaje === "3" ? "Rechazado: " : "Código " + R.mensaje + ": ") + R.detalle);
  if (F && R) {
    add("La respuesta corresponde a la factura", F.clave === R.clave ? "ok" : "no", F.clave === R.clave ? "Misma clave" : "Las claves no coinciden");
    add("Total igual en factura y respuesta", Math.abs(F.total - R.total) <= tol ? "ok" : "no", `${fmt(F.total)} / ${fmt(R.total)}`);
    add("IVA igual en factura y respuesta", Math.abs(F.impuesto - R.impuesto) <= tol ? "ok" : "no", `${fmt(F.impuesto)} / ${fmt(R.impuesto)}`);
  }
  if (pdf && F) {
    if (pdf.texto == null || pdf.texto.trim().length < 30) add("El PDF corresponde a la factura", "nv", "PDF escaneado o sin texto: la Universidad lo revisará visualmente.");
    else {
      const dig = digitos(pdf.texto);
      add("El PDF corresponde a la factura (clave)", dig.includes(F.clave) ? "ok" : "no", dig.includes(F.clave) ? "" : "La clave del XML no aparece en el PDF.");
      add("Total del PDF igual al XML", montosEn(pdf.texto).some(m => Math.abs(m - F.total) <= tol) ? "ok" : "no", fmt(F.total));
    }
  }
  if (S.envios.some(e => e.clave && F && e.clave === F.clave)) add("Factura no enviada antes", "no", "Ya envió esta factura.");
  S.analisis = { controles: c, factura: F, respuesta: R };
  const completos = pdf && F && R;
  $("#verificacion").innerHTML = c.length ? `<b>Verificación inmediata</b> <span class="sub">(${c.filter(x => x.estado === "ok").length} de ${c.length} correctos)</span>
    <ul class="controles">${c.map(x => `<li>${marca(x.estado)}<span><b>${esc(x.control)}</b>${x.detalle ? " · " + esc(x.detalle) : ""}</span></li>`).join("")}</ul>` : "";
  const puede = completos && S.registro && !c.some(x => x.control === "Factura no enviada antes" && x.estado === "no");
  $("#btnEnviar").disabled = !puede;
  $("#ayudaEnvio").textContent = !S.registro ? "Primero guarde su registro." : !completos ? "Cargue los tres archivos de la misma factura."
    : c.some(x => x.estado === "no") ? "Hay diferencias: puede enviarla igual, pero probablemente se la devolverán." : "Todo coincide. Puede enviarla.";
}

async function cargarArchivo(tipo, input, ranura) {
  const archivo = input.files[0];
  if (!archivo) return;
  const r = $(ranura);
  r.querySelector(".nombre").textContent = `${archivo.name} · ${(archivo.size / 1024).toFixed(0)} KB`;
  r.classList.add("lleno");
  if (tipo === "pdf") {
    if (archivo.size > 2 * 1024 * 1024) { mensaje("#msgEnvio", "El PDF supera 2 MB. Exporte una versión más liviana.", "error"); input.value = ""; return; }
    const buffer = await archivo.arrayBuffer();
    S.archivos.pdf = { nombre: archivo.name, tamano: archivo.size, buffer, texto: await textoPdf(buffer) };
  } else {
    const texto = await archivo.text();
    S.archivos[tipo] = { nombre: archivo.name, texto, datos: leerXml(texto) };
  }
  verificar();
}
$("#fPdf").onchange = e => cargarArchivo("pdf", e.target, "#rPdf");
$("#fXml").onchange = e => cargarArchivo("xml", e.target, "#rXml");
$("#fResp").onchange = e => cargarArchivo("resp", e.target, "#rResp");
function limpiar() {
  S.archivos = { pdf: null, xml: null, resp: null }; S.analisis = null;
  ["#fPdf", "#fXml", "#fResp"].forEach(s => $(s).value = "");
  ["#rPdf", "#rXml", "#rResp"].forEach(s => { $(s).classList.remove("lleno"); $(s).querySelector(".nombre").textContent = "Ningún archivo"; });
  $("#verificacion").innerHTML = ""; $("#btnEnviar").disabled = true; verificar();
}
$("#btnLimpiar").onclick = () => { limpiar(); mensaje("#msgEnvio", ""); };

// ------------------------------------------------------------ vista proveedor
function aB64(buffer) { let s = ""; const b = new Uint8Array(buffer);
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000)); return btoa(s); }

async function cargarProveedor() {
  const uid = S.me.id;
  const [reg, est, env, estEnv] = await Promise.all([
    S.DB.doc("proveedores/" + uid).get(), S.DB.doc("estado_proveedores/" + uid).get(),
    S.DB.collection("envios/" + uid + "/facturas").get(), S.DB.doc("estado_envios/" + uid).get()]);
  S.registro = reg.exists ? reg.data() : null;
  S.estadoReg = est.exists ? est.data() : null;
  S.envios = env.docs.map(d => ({ id: d.id, ...d.data() })).sort((a, b) => (b.ts || "").localeCompare(a.ts || ""));
  S.estados = estEnv.exists ? (estEnv.data().items || {}) : {};
  renderProveedor();
}
function renderProveedor() {
  const r = S.registro, e = S.estadoReg;
  if (r) {
    const estado = e?.estado || "Pendiente";
    $("#registroResumen").innerHTML = `<dl class="datos"><dt>Estado</dt><dd>${pill(estado === "Aprobado" ? "Aprobado" : estado === "Rechazado" ? "Rechazado" : "Pendiente de aprobación",
      estado === "Aprobado" ? "ok" : estado === "Rechazado" ? "no" : "pend")}${e?.comentario ? " · " + esc(e.comentario) : ""}</dd>
      <dt>Cédula</dt><dd>${esc(r.cedula)}</dd><dt>Razón social</dt><dd>${esc(r.razon_social)}</dd><dt>Correo</dt><dd>${esc(r.correo)}</dd></dl>
      <button class="btn-link" type="button" id="editarRegistro">Editar mis datos</button>`;
    $("#formRegistro").hidden = true;
    $("#editarRegistro").onclick = () => { $("#formRegistro").hidden = false; $("#editarRegistro").hidden = true; };
    $("#pCedula").value = r.cedula; $("#pRazon").value = r.razon_social; $("#pComercial").value = r.nombre_comercial || "";
    $("#pCorreo").value = r.correo; $("#pTelefono").value = r.telefono || "";
  } else {
    $("#registroResumen").innerHTML = '<p class="sub" style="margin:0 0 10px">Complete sus datos una sola vez. La Universidad aprueba el registro antes de pagar.</p>';
    $("#formRegistro").hidden = false;
  }
  const filas = S.envios.map(x => { const est = S.estados[x.id] || { estado: "RECIBIDO" }; const [t, c] = ESTADOS_ENVIO[est.estado] || [est.estado, ""];
    const ok = (x.controles || []).filter(k => k.estado === "ok").length;
    return `<tr><td>${esc(fh(x.ts))}</td><td>${esc(x.consecutivo)}<div class="sub">${esc(x.fecha)}</div></td><td class="n">${fmt(x.total)}</td>
      <td>${ok} de ${(x.controles || []).length} correctos</td><td>${pill(t, c)}${est.comentario ? `<div class="sub">${esc(est.comentario)}</div>` : ""}</td></tr>`; });
  $("#tMisEnvios").innerHTML = filas.length ? `<table><thead><tr><th>Enviada</th><th>Factura</th><th style="text-align:right">Total</th><th>Verificación</th><th>Estado</th></tr></thead><tbody>${filas.join("")}</tbody></table>`
    : '<div class="vacio">Todavía no ha enviado facturas.</div>';
  verificar();
}
$("#formRegistro").addEventListener("submit", async ev => {
  ev.preventDefault();
  const datos = { cedula: $("#pCedula").value.trim(), razon_social: $("#pRazon").value.trim(), nombre_comercial: $("#pComercial").value.trim(),
                  correo: $("#pCorreo").value.trim(), telefono: $("#pTelefono").value.trim(), ts: new Date().toISOString() };
  if (digitos(datos.cedula).length < 9) return mensaje("#msgRegistro", "La cédula debe tener al menos 9 dígitos.", "error");
  $("#btnRegistro").disabled = true;
  try { await S.DB.doc("proveedores/" + S.me.id).set(datos); S.registro = datos; mensaje("#msgRegistro", "Registro guardado. Queda pendiente de aprobación.", "exito"); renderProveedor(); }
  catch (e) { mensaje("#msgRegistro", e?.code === "invalid_argument" ? "Su acceso no permite registrarse. Pida a la Universidad acceso de Colaborador." : "No se pudo guardar. Intente de nuevo.", "error"); }
  finally { $("#btnRegistro").disabled = false; }
});
$("#btnEnviar").onclick = async () => {
  const { pdf, xml, resp } = S.archivos, F = S.analisis.factura;
  const id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())).replace(/-/g, "").slice(0, 20);
  const b64 = aB64(pdf.buffer), partes = [];
  for (let i = 0; i < b64.length; i += 200000) partes.push(b64.slice(i, i + 200000));
  $("#btnEnviar").disabled = true; mensaje("#msgEnvio", `Enviando (${partes.length + 1} partes)…`);
  try {
    const base = "envios/" + S.me.id;
    for (let i = 0; i < partes.length; i++) await S.DB.doc(`${base}/pdf/${id}-${i}`).set({ data: partes[i] });
    await S.DB.doc(`${base}/facturas/${id}`).set({ ts: new Date().toISOString(), clave: F.clave, consecutivo: F.consecutivo, fecha: F.fecha,
      emisor: F.emisor, emisor_nombre: F.emisorNombre, total: F.total, impuesto: F.impuesto, hacienda: S.analisis.respuesta?.mensaje || "",
      xml_factura: xml.texto, xml_respuesta: resp.texto, pdf_nombre: pdf.nombre, pdf_tamano: pdf.tamano, pdf_partes: partes.length,
      controles: S.analisis.controles });
    await S.DB.doc(base).set({ ultimo: new Date().toISOString() });
    mensaje("#msgEnvio", "Factura enviada. Verá aquí el resultado de la revisión.", "exito");
    limpiar(); await cargarProveedor();
  } catch (e) {
    mensaje("#msgEnvio", e?.code === "invalid_argument" ? "Su acceso no permite enviar. Pida a la Universidad acceso de Colaborador."
      : e?.code === "quota_exceeded" ? "El portal llegó a su capacidad. Avise a la Universidad." : "No se pudo enviar. Intente de nuevo.", "error");
    $("#btnEnviar").disabled = false;
  }
};

// ------------------------------------------------------------ vista administrador
async function cargarAdmin() {
  mensaje("#estadoPagina", "Cargando información de proveedores…");
  try {
    const [regs, estP, envP, estE] = await Promise.all([S.DB.collection("proveedores").get(), S.DB.collection("estado_proveedores").get(),
      S.DB.collection("envios").get(), S.DB.collection("estado_envios").get()]);
    S.adminProv = regs.docs.map(d => ({ uid: d.id, ...d.data() }));
    S.adminEstadoProv = Object.fromEntries(estP.docs.map(d => [d.id, d.data()]));
    S.adminEstadoEnv = Object.fromEntries(estE.docs.map(d => [d.id, d.data().items || {}]));
    S.adminEnvios = [];
    await Promise.all(envP.docs.map(async p => { const f = await S.DB.collection("envios/" + p.id + "/facturas").get();
      f.docs.forEach(d => S.adminEnvios.push({ uid: p.id, id: d.id, ...d.data() })); }));
    S.adminEnvios.sort((a, b) => (b.ts || "").localeCompare(a.ts || ""));
    mensaje("#estadoPagina", "");
    renderAdmin();
  } catch (e) { mensaje("#estadoPagina", "No se pudo leer la información de proveedores. Use Actualizar.", "error"); }
}
function renderAdmin() {
  const prov = S.adminProv, env = S.adminEnvios, estP = uid => (S.adminEstadoProv[uid] || {}).estado || "Pendiente";
  const conDif = env.filter(x => (x.controles || []).some(k => k.estado === "no")).length;
  const kpi = (l, v) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  $("#kpisAdmin").innerHTML = kpi("Proveedores registrados", prov.length) + kpi("Pendientes de aprobar", prov.filter(p => estP(p.uid) === "Pendiente").length)
    + kpi("Facturas recibidas", env.length) + kpi("Con diferencias", conDif);
  $("#tProveedores").innerHTML = prov.length ? `<table><thead><tr><th>Proveedor</th><th>Cédula</th><th>Correo</th><th>Registrado</th><th>Estado</th><th></th></tr></thead><tbody>${
    prov.map(p => { const e = estP(p.uid); return `<tr><td><b>${esc(p.razon_social)}</b>${p.nombre_comercial ? `<div class="sub">${esc(p.nombre_comercial)}</div>` : ""}</td>
      <td>${esc(p.cedula)}</td><td>${esc(p.correo)}<div class="sub">${esc(p.telefono)}</div></td><td>${esc(fh(p.ts))}</td>
      <td>${pill(e, e === "Aprobado" ? "ok" : e === "Rechazado" ? "no" : "pend")}</td>
      <td><div class="acciones"><button class="btn-link" type="button" data-prov="${esc(p.uid)}" data-estado="Aprobado">Aprobar</button>
      <button class="btn-link" type="button" data-prov="${esc(p.uid)}" data-estado="Rechazado">Rechazar</button></div></td></tr>`; }).join("")}</tbody></table>`
    : '<div class="vacio">Ningún proveedor se ha registrado todavía.</div>';
  const nombreProv = uid => (prov.find(p => p.uid === uid) || {}).razon_social || "Proveedor sin registro";
  $("#tEnvios").innerHTML = env.length ? `<table><thead><tr><th>Recibida</th><th>Proveedor</th><th>Factura</th><th style="text-align:right">Total</th><th>Verificación</th><th>Estado</th><th></th></tr></thead><tbody>${
    env.map(x => { const ok = (x.controles || []).filter(k => k.estado === "ok").length, est = (S.adminEstadoEnv[x.uid] || {})[x.id] || { estado: "RECIBIDO" };
      const [t, c] = ESTADOS_ENVIO[est.estado] || [est.estado, ""];
      return `<tr><td>${esc(fh(x.ts))}</td><td><b>${esc(nombreProv(x.uid))}</b><div class="sub">${esc(x.emisor)}</div></td>
        <td>${esc(x.consecutivo)}<div class="sub">${esc(x.fecha)}</div></td><td class="n">${fmt(x.total)}</td>
        <td><details><summary>${ok} de ${(x.controles || []).length} correctos</summary><ul class="controles">${(x.controles || []).map(k =>
          `<li>${marca(k.estado)}<span><b>${esc(k.control)}</b>${k.detalle ? " · " + esc(k.detalle) : ""}</span></li>`).join("")}</ul></details></td>
        <td>${pill(t, c)}</td>
        <td>${S.downloads ? `<div class="acciones"><button class="btn-link" type="button" data-bajar="pdf" data-uid="${esc(x.uid)}" data-id="${esc(x.id)}">PDF</button>
          <button class="btn-link" type="button" data-bajar="xml" data-uid="${esc(x.uid)}" data-id="${esc(x.id)}">XML</button>
          <button class="btn-link" type="button" data-bajar="resp" data-uid="${esc(x.uid)}" data-id="${esc(x.id)}">Respuesta</button></div>` : ""}</td></tr>`; }).join("")}</tbody></table>`
    : '<div class="vacio">No hay facturas recibidas.</div>';
}
document.addEventListener("click", async ev => {
  const b = ev.target.closest("[data-prov]");
  if (b && S.admin) {
    b.disabled = true;
    try { await S.DB.doc("estado_proveedores/" + b.dataset.prov).set({ estado: b.dataset.estado, ts: new Date().toISOString() });
      S.adminEstadoProv[b.dataset.prov] = { estado: b.dataset.estado }; renderAdmin(); }
    catch (e) { mensaje("#estadoPagina", "No se pudo cambiar el estado del proveedor.", "error"); b.disabled = false; }
    return;
  }
  const d = ev.target.closest("[data-bajar]");
  if (d && S.admin && S.downloads) {
    const x = S.adminEnvios.find(e => e.uid === d.dataset.uid && e.id === d.dataset.id);
    try {
      if (d.dataset.bajar === "pdf") {
        let b64 = "";
        for (let i = 0; i < x.pdf_partes; i++) b64 += (await S.DB.doc(`envios/${x.uid}/pdf/${x.id}-${i}`).get()).data().data;
        const bin = atob(b64), bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        await S.downloads.save({ filename: x.pdf_nombre || `Factura_${x.consecutivo}.pdf`, data: new Blob([bytes]) });
      } else {
        await S.downloads.save({ filename: `${d.dataset.bajar === "xml" ? "Factura" : "Respuesta"}_${x.consecutivo}.xml`,
                                 data: d.dataset.bajar === "xml" ? x.xml_factura : x.xml_respuesta });
      }
    } catch (e) { if (e?.code !== "declined") mensaje("#estadoPagina", "No se pudo descargar el archivo.", "error"); }
  }
});
$("#btnActualizar").onclick = cargarAdmin;

// ------------------------------------------------------------ inicio y selector de vista
function mostrarVista(v) {
  S.vista = v;
  document.querySelectorAll("#selector button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.vista === v)));
  $("#vistaProveedor").hidden = v !== "proveedor"; $("#vistaAdmin").hidden = v !== "admin";
  try { localStorage.setItem("portal-vista", v); } catch (e) {}
  if (v === "admin") cargarAdmin(); else cargarProveedor();
}
document.querySelectorAll("#selector button").forEach(b => b.onclick = () => mostrarVista(b.dataset.vista));

async function iniciar() {
  if (!window.claude || !window.claude.use) return mensaje("#estadoPagina", "Abra el portal desde su enlace oficial de claude.ai.", "error");
  const [U, DB] = await Promise.all([claude.use("user"), claude.use("db")]);
  if (!U || !DB) return mensaje("#estadoPagina", "El portal no está disponible en esta vista. Abra el enlace con su cuenta.", "error");
  const me = await U.me();
  if (!me.id) return mensaje("#estadoPagina", "Inicie sesión para usar el portal.", "error");
  Object.assign(S, { U, DB, me, admin: me.canEdit || me.isOwner });
  claude.use("downloads").then(d => { S.downloads = d; if (S.vista === "admin") renderAdmin(); });
  mensaje("#estadoPagina", "");
  let vista = "proveedor";
  if (S.admin) {
    $("#selector").hidden = false;
    try { vista = localStorage.getItem("portal-vista") || "admin"; } catch (e) { vista = "admin"; }
  }
  mostrarVista(vista);
}
iniciar();
</script>
"""
