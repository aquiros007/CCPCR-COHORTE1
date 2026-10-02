"""Genera el dashboard HTML (autocontenido, sin dependencias externas) a partir de la base de datos."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from .db import BaseDatos
from .reglas import REGLAS


def clave_hallazgo(h: dict) -> str:
    """Identificador estable del hallazgo (sobrevive a reprocesos) para ligar las validaciones."""
    base = "|".join(str(h.get(k) or "") for k in ("origen", "caja", "liquidacion", "fecha", "fila", "regla", "detalle"))
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def _datos(db: BaseDatos, catalogo: dict) -> dict:
    facturas = db.consultar("""
        SELECT f.id, f.caja, COALESCE(f.fecha, l.fecha) AS fecha, f.total_crc AS monto, f.categoria, f.proveedor,
               f.estado, f.consecutivo, l.numero AS liquidacion, l.custodio
        FROM facturas f JOIN liquidaciones l ON l.id = f.liquidacion_id""")
    liquidaciones = db.consultar("""
        SELECT id, caja, custodio, numero, fecha, total_facturas AS total, n_facturas, n_rechazadas,
               n_observadas, estado FROM liquidaciones ORDER BY fecha DESC""")
    arqueos = db.consultar("""
        SELECT id, caja, custodio, fecha, realizado_por, fondo, efectivo, pendientes_facturas, vales,
               diferencia, estado FROM arqueos ORDER BY fecha DESC""")
    hallazgos = db.consultar("""
        SELECT h.id, h.caja, h.severidad, h.regla, h.detalle, h.monto, h.estado, h.origen,
               COALESCE(f.fecha, l.fecha, a.fecha) AS fecha, l.numero AS liquidacion,
               f.proveedor, f.fila, h.factura_relacionada_id AS relacionada
        FROM hallazgos h
        LEFT JOIN facturas f ON f.id = h.factura_id
        LEFT JOIN liquidaciones l ON l.id = h.liquidacion_id
        LEFT JOIN arqueos a ON a.id = h.arqueo_id""")
    for h in hallazgos:
        h["titulo"] = REGLAS.get(h["regla"], h["regla"])
        h["clave"] = clave_hallazgo(h)
    ultimas = {r["caja"]: r for r in db.consultar(
        "SELECT caja, MAX(fecha) AS ult_liq, COUNT(*) AS n_liq FROM liquidaciones GROUP BY caja")}
    ult_arq = {r["caja"]: r["ult_arq"] for r in db.consultar("SELECT caja, MAX(fecha) AS ult_arq FROM arqueos GROUP BY caja")}
    unidades = [{"caja": c, "unidad": i["unidad"], "responsable": i["responsable"], "fondo": i["fondo"],
                 "activa": i["activa"], "ult_liq": (ultimas.get(c) or {}).get("ult_liq"),
                 "n_liq": (ultimas.get(c) or {}).get("n_liq", 0), "ult_arq": ult_arq.get(c)}
                for c, i in catalogo.items()]
    return {"unidades": unidades, "facturas": facturas, "liquidaciones": liquidaciones, "arqueos": arqueos, "hallazgos": hallazgos,
            "generado": datetime.now().strftime("%d/%m/%Y %H:%M")}


def generar_dashboard(ruta_db: Path, destinos: list[Path], institucion: str = "", catalogo: dict | None = None,
                      aviso: str = "") -> list[Path]:
    db = BaseDatos(ruta_db)
    datos = _datos(db, catalogo or {})
    db.cerrar()
    html = PLANTILLA.replace("__DATOS__", json.dumps(datos, ensure_ascii=False, default=str).replace("</", "<\\/"))
    html = html.replace("__INSTITUCION__", institucion or "")
    html = html.replace("__AVISO__", f'<span class="aviso">{aviso}</span>' if aviso else "")
    escritos = []
    for d in destinos:
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(html, encoding="utf-8")
        escritos.append(d)
    return escritos


PLANTILLA = r"""<title>Control de Caja Chica</title>
<style>
:root {
  color-scheme: light;
  --surface-0: #f4f4f2; --surface-1: #fcfcfb; --border: #e3e2de; --grid: #ecebe7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #7a7974;
  --series-1: #2a78d6; --accent: #1f3a5f;
  --good: #0ca30c; --warning: #fab219; --serious: #ec835a; --critical: #d03b3b;
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
body { margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
header { padding: 20px 24px 8px; }
h1 { margin: 0; font-size: 22px; } h2 { font-size: 15px; margin: 0 0 10px; }
.sub { color: var(--text-secondary); font-size: 13px; }
main { padding: 8px 24px 40px; max-width: 1400px; margin: 0 auto; }
.filtros { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 10px 0 18px; }
.filtros label { display: flex; flex-direction: column; font-size: 12px; color: var(--text-secondary); gap: 4px; }
select, input { font: inherit; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--surface-1); color: var(--text-primary); }
.chips { display: flex; gap: 4px; }
.chips button { font: inherit; font-size: 12px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--surface-1); color: var(--text-secondary); cursor: pointer; }
.chips button.on { background: var(--accent); color: var(--surface-1); border-color: var(--accent); }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 16px; }
.kpi, .card { min-width: 0; background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.kpi .v { font-size: 24px; font-weight: 650; margin-top: 2px; font-variant-numeric: tabular-nums; }
.kpi .l { font-size: 12px; color: var(--text-secondary); }
.kpi .d { font-size: 12px; color: var(--text-muted); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr)); gap: 16px; margin-bottom: 16px; }
.card.full { grid-column: 1 / -1; }
svg text { fill: var(--text-secondary); font-size: 11px; }
.leyenda { display: flex; gap: 14px; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; flex-wrap: wrap; }
.leyenda i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; color: var(--text-secondary); font-weight: 600; border-bottom: 1px solid var(--border); padding: 6px 8px; position: sticky; top: 0; background: var(--surface-1); }
td { border-bottom: 1px solid var(--grid); padding: 6px 8px; vertical-align: top; }
td:nth-child(2) { white-space: nowrap; }
td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.tabla { max-height: 420px; overflow: auto; }
.pill { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.pill.ALTA, .pill.RECHAZADA, .pill.FALTA { background: var(--critical-bg); }
.pill.MEDIA, .pill.OBSERVADA { background: var(--warning-bg); }
.pill.BAJA { background: var(--neutral-bg); }
.pill.OK, .pill.CUADRADO, .pill.APROBABLE { background: var(--good-bg); }
.pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.pill.ALTA::before, .pill.RECHAZADA::before { background: var(--critical); }
.pill.MEDIA::before, .pill.OBSERVADA::before { background: var(--warning); }
.pill.BAJA::before { background: var(--text-muted); }
.pill.OK::before, .pill.CUADRADO::before, .pill.APROBABLE::before { background: var(--good); }
.tip { position: fixed; pointer-events: none; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,.12); display: none; z-index: 10; }
.tip b { display: block; margin-bottom: 2px; }
.vacio { color: var(--text-muted); padding: 20px 0; text-align: center; }
.barra-tabla { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
@media (max-width: 640px) { main, header { padding-left: 16px; padding-right: 16px; } .grid { grid-template-columns: 1fr; } }
[hidden] { display: none !important; }
.aviso { display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px; background: var(--warning-bg); color: var(--text-primary); font-size: 12px; font-weight: 600; }
button.btn { font: inherit; font-weight: 600; padding: 8px 14px; border-radius: 8px; border: 1px solid var(--accent); background: var(--accent); color: var(--surface-1); cursor: pointer; }
button.btn.sec { background: var(--surface-1); color: var(--text-primary); border-color: var(--border); }
button.btn:disabled { opacity: .55; cursor: default; }
button:focus-visible, select:focus-visible, input:focus-visible, textarea:focus-visible { outline: 2px solid var(--series-1); outline-offset: 2px; }
.btn-link { font: inherit; font-size: 12px; font-weight: 600; color: var(--series-1); background: none; border: 0; padding: 2px 0; cursor: pointer; display: block; }
textarea { font: inherit; padding: 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-1); color: var(--text-primary); width: 100%; min-height: 76px; resize: vertical; }
.capa { position: fixed; inset: 0; background: color-mix(in srgb, var(--surface-0) 70%, transparent); display: grid; place-items: center; padding: 16px; z-index: 20; overflow-y: auto; }
.panel { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 22px; width: min(520px, 100%); box-shadow: 0 12px 40px rgba(0,0,0,.18); display: grid; gap: 14px; }
.panel h2 { font-size: 18px; margin: 0; text-wrap: balance; }
.panel p { margin: 0; color: var(--text-secondary); }
.campo { display: grid; gap: 5px; font-size: 13px; font-weight: 600; }
.campo span.ayuda { font-weight: 400; color: var(--text-muted); font-size: 12px; }
.identidad { display: flex; gap: 12px; align-items: center; padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-0); }
.identidad img { width: 36px; height: 36px; border-radius: 50%; }
.identidad b { display: block; }
.decl { display: flex; gap: 8px; align-items: flex-start; font-size: 13px; color: var(--text-secondary); }
.decl input { margin-top: 3px; }
.opciones { display: grid; gap: 6px; }
.opciones label { display: flex; gap: 8px; align-items: center; padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; font-weight: 500; }
.opciones label:has(input:checked) { border-color: var(--series-1); background: color-mix(in srgb, var(--series-1) 8%, var(--surface-1)); }
.acciones { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
.error { color: var(--critical); font-size: 13px; }
.sesion { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; justify-content: space-between; margin: 8px 0 4px; padding: 10px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-1); font-size: 13px; }
.sesion .quien { color: var(--text-secondary); }
.sesion .quien b { color: var(--text-primary); }
.resumen-h { font-size: 13px; padding: 10px 12px; border-radius: 8px; background: var(--surface-0); border: 1px solid var(--border); }
.pill.V-CONFIRMADO { background: var(--critical-bg); } .pill.V-CONFIRMADO::before { background: var(--critical); }
.pill.V-JUSTIFICADO, .pill.V-FALSO { background: var(--good-bg); } .pill.V-JUSTIFICADO::before, .pill.V-FALSO::before { background: var(--good); }
.pill.V-INFO { background: var(--warning-bg); } .pill.V-INFO::before { background: var(--warning); }
.pill.T-ingreso { background: var(--neutral-bg); } .pill.T-ingreso::before { background: var(--series-1); }
.pill.T-vigencia { background: var(--good-bg); } .pill.T-vigencia::before { background: var(--good); }
.pill.T-validacion { background: var(--warning-bg); } .pill.T-validacion::before { background: var(--warning); }
</style>

<div class="capa" id="puerta" role="dialog" aria-modal="true" aria-labelledby="puertaTitulo">
  <div class="panel">
    <h2 id="puertaTitulo">Registro de revisión</h2>
    <p id="puertaCargando">Verificando su identidad…</p>
    <form id="puertaForm" hidden>
      <div style="display:grid;gap:14px">
        <p>Cada ingreso queda registrado a su nombre, con la fecha de corte de la información que revisa.</p>
        <div class="identidad"><img id="idAvatar" alt=""><div><b id="idNombre"></b><span class="sub" id="idCorreo"></span></div></div>
        <label class="campo" for="rRol">Rol en esta revisión<select id="rRol" required></select></label>
        <label class="campo" for="rMotivo">Motivo del ingreso<select id="rMotivo" required></select></label>
        <label class="campo" for="rAlcance">Unidades o cajas que revisará <span class="ayuda">Opcional. Ej.: CAJA-ADM, CAJA-OPS</span>
          <input id="rAlcance" maxlength="200"></label>
        <label class="decl" for="rDecl"><input type="checkbox" id="rDecl" required>
          <span>Confirmo que revisaré la información con corte al <b class="corte"></b> y que las validaciones que registre quedan a mi nombre.</span></label>
        <div class="error" id="puertaError" hidden></div>
        <div class="acciones"><button class="btn" type="submit" id="puertaBtn">Registrarme e ingresar</button></div>
      </div>
    </form>
    <div id="puertaAviso" hidden style="display:grid;gap:8px">
      <b id="avisoTitulo"></b><p id="avisoTexto"></p>
    </div>
  </div>
</div>

<div class="capa" id="dlgValidar" hidden role="dialog" aria-modal="true" aria-labelledby="valTitulo">
  <form class="panel" id="valForm">
    <h2 id="valTitulo">Validar evidencia del hallazgo</h2>
    <div class="resumen-h" id="valResumen"></div>
    <div class="campo">Resultado de la validación
      <div class="opciones" id="valOpciones"></div></div>
    <label class="campo" for="valComentario">Evidencia revisada y conclusión <span class="ayuda">Obligatorio. Indique qué documento revisó y por qué concluye esto.</span>
      <textarea id="valComentario" minlength="10" maxlength="1000" required></textarea></label>
    <div class="error" id="valError" hidden></div>
    <div class="acciones"><button class="btn sec" type="button" id="valCancelar">Cancelar</button><button class="btn" type="submit" id="valBtn">Registrar validación</button></div>
  </form>
</div>

<div class="capa" id="dlgVigencia" hidden role="dialog" aria-modal="true" aria-labelledby="vigTitulo">
  <form class="panel" id="vigForm">
    <h2 id="vigTitulo">Confirmar que la información está al día</h2>
    <p>Corte de la información: <b class="corte"></b>. Su confirmación queda registrada a su nombre.</p>
    <div class="opciones">
      <label><input type="radio" name="vig" value="AL_DIA" required> La información está al día</label>
      <label><input type="radio" name="vig" value="DESACTUALIZADA"> Faltan liquidaciones o arqueos recientes</label>
      <label><input type="radio" name="vig" value="INCONSISTENTE"> Hay datos que no coinciden con los documentos</label>
    </div>
    <label class="campo" for="vigComentario">Observaciones <span class="ayuda">Obligatorio si la información no está al día.</span>
      <textarea id="vigComentario" maxlength="1000"></textarea></label>
    <div class="error" id="vigError" hidden></div>
    <div class="acciones"><button class="btn sec" type="button" id="vigCancelar">Cancelar</button><button class="btn" type="submit" id="vigBtn">Registrar confirmación</button></div>
  </form>
</div>

<header>
  <h1>Control de Caja Chica</h1>
  <div class="sub">__INSTITUCION__ · Información con corte al <span id="gen"></span>__AVISO__</div>
</header>
<main id="app" hidden>
  <div class="sesion">
    <div class="quien" id="sesionTexto"></div>
    <button class="btn sec" type="button" id="vigAbrir">Confirmar que la información está al día</button>
  </div>
  <div class="filtros">
    <label>Caja <select id="fCaja"></select></label>
    <label>Desde <input type="date" id="fDesde"></label>
    <label>Hasta <input type="date" id="fHasta"></label>
    <div class="chips" id="rangos">
      <button data-d="28">4 semanas</button><button data-d="91">12 semanas</button>
      <button data-d="365">12 meses</button><button data-d="0" class="on">Todo</button>
    </div>
  </div>

  <div class="kpis" id="kpis"></div>

  <div class="grid">
    <div class="card full"><h2>Gasto semanal por resultado de la revisión</h2>
      <div class="leyenda"><span><i style="background:var(--good)"></i>OK</span>
        <span><i style="background:var(--warning)"></i>Observada</span>
        <span><i style="background:var(--critical)"></i>Rechazada</span></div>
      <div id="gSemanal"></div></div>
    <div class="card"><h2>Gasto por categoría</h2><div id="gCategoria"></div></div>
    <div class="card"><h2>Gasto por caja</h2><div id="gCaja"></div></div>
    <div class="card"><h2>Top 10 proveedores</h2><div id="gProveedor"></div></div>
    <div class="card"><h2>Hallazgos por tipo (ALTA y MEDIA)</h2><div id="gHallazgos"></div></div>
  </div>

  <div class="grid">
    <div class="card full"><h2>Hallazgos</h2>
      <div class="barra-tabla">
        <select id="fSev"><option value="">Todas las severidades</option><option>ALTA</option><option>MEDIA</option><option>BAJA</option></select>
        <input id="fBuscar" placeholder="Buscar proveedor, regla, liquidación…" style="flex:1;min-width:200px">
      </div>
      <div class="tabla" id="tHallazgos"></div></div>
    <div class="card full"><h2>Facturas duplicadas o posibles duplicados</h2><div class="tabla" id="tDuplicados"></div></div>
    <div class="card full"><h2>Entregas por unidad de negocio</h2>
      <div class="barra-tabla"><input id="fUnidad" placeholder="Buscar unidad o responsable…" style="flex:1;min-width:200px"></div>
      <div class="tabla" id="tUnidades"></div></div>
    <div class="card"><h2>Liquidaciones</h2><div class="tabla" id="tLiquidaciones"></div></div>
    <div class="card"><h2>Arqueos</h2><div class="tabla" id="tArqueos"></div></div>
  </div>

  <div class="grid" id="bitacora" hidden>
    <div class="card full"><h2>Bitácora de revisión</h2>
      <p class="sub" style="margin:0 0 10px">Quién ingresó, qué confirmó y qué evidencia validó. Solo la ven el administrador y los editores del dashboard.</p>
      <div class="barra-tabla">
        <select id="bTipo"><option value="">Todos los registros</option><option value="ingreso">Ingresos</option><option value="vigencia">Confirmaciones de vigencia</option><option value="validacion">Validaciones de evidencia</option></select>
        <input id="bBuscar" placeholder="Buscar persona, caja, motivo…" style="flex:1;min-width:200px">
        <button class="btn sec" type="button" id="bActualizar">Actualizar</button>
        <button class="btn sec" type="button" id="bDescargar" hidden>Descargar CSV</button>
      </div>
      <div class="sub" id="bEstado"></div>
      <div class="tabla" id="tBitacora"></div></div>
  </div>
</main>
<div class="tip" id="tip"></div>
<script>
const D = __DATOS__;
const $ = s => document.querySelector(s);
const fmt = n => n == null ? "—" : (n < 0 ? "−" : "") + "₡" + Math.abs(Math.round(n)).toLocaleString("es-CR");
const corto = n => { const a = Math.abs(n), s = n < 0 ? "−" : ""; return s + (a >= 1e6 ? "₡" + (a/1e6).toFixed(1) + " M" : a >= 1e3 ? "₡" + Math.round(a/1e3) + " k" : "₡" + Math.round(a)); };
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fdate = s => s ? s.slice(0,10).split("-").reverse().join("/") : "—";
const CLASE = { "CON RECHAZOS": "ALTA", "CON HALLAZGOS GRAVES": "ALTA", "CON OBSERVACIONES": "MEDIA" };
const pill = s => `<span class="pill ${CLASE[s] || esc(s)}">${esc(s)}</span>`;
$("#gen").textContent = D.generado;

// ---------- filtros
const cajas = [...new Set([...D.unidades, ...D.facturas, ...D.arqueos].map(x => x.caja))].sort();
const nombreUnidad = Object.fromEntries(D.unidades.map(u => [u.caja, u.unidad]));
$("#fCaja").innerHTML = `<option value="">Todas (${cajas.length})</option>` + cajas.map(c => `<option value="${esc(c)}">${esc(c)}${nombreUnidad[c] ? " · " + esc(nombreUnidad[c]) : ""}</option>`).join("");
const F = { caja: "", desde: "", hasta: "" };
try { Object.assign(F, JSON.parse(localStorage.getItem("cc-filtros") || "{}")); } catch (e) {}
$("#fCaja").value = F.caja; $("#fDesde").value = F.desde; $("#fHasta").value = F.hasta;
const pasa = x => (!F.caja || x.caja === F.caja) && (!F.desde || (x.fecha || "") >= F.desde) && (!F.hasta || (x.fecha || "") <= F.hasta);
function cambiar() {
  F.caja = $("#fCaja").value; F.desde = $("#fDesde").value; F.hasta = $("#fHasta").value;
  try { localStorage.setItem("cc-filtros", JSON.stringify(F)); } catch (e) {}
  render();
}
["#fCaja", "#fDesde", "#fHasta"].forEach(s => $(s).addEventListener("change", () => { document.querySelectorAll("#rangos button").forEach(b => b.classList.remove("on")); cambiar(); }));
document.querySelectorAll("#rangos button").forEach(b => b.onclick = () => {
  document.querySelectorAll("#rangos button").forEach(x => x.classList.toggle("on", x === b));
  const d = +b.dataset.d;
  $("#fHasta").value = ""; $("#fDesde").value = d ? new Date(Date.now() - d * 864e5).toISOString().slice(0,10) : "";
  cambiar();
});
$("#fSev").onchange = render; $("#fBuscar").oninput = render; $("#fUnidad").oninput = render;

// ---------- tooltip
const tip = $("#tip");
function mostrar(e, html) { tip.innerHTML = html; tip.style.display = "block";
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8); tip.style.left = x + "px"; tip.style.top = (e.clientY + 14) + "px"; }
function ocultar() { tip.style.display = "none"; }
function enlazarTips(cont) { cont.querySelectorAll("[data-tip]").forEach(el => {
  el.addEventListener("mousemove", e => mostrar(e, el.dataset.tip)); el.addEventListener("mouseleave", ocultar); }); }

// ---------- gráficos SVG
function barrasH(id, filas, color = "var(--series-1)", etiqueta = fmt, izqMax = 190) {
  const cont = $(id);
  if (!filas.length) { cont.innerHTML = '<div class="vacio">Sin datos para el filtro</div>'; return; }
  const W = cont.clientWidth || 500, fila = 26, izq = Math.min(izqMax, W * 0.45), der = 84, maxC = Math.floor((izq - 12) / 6);
  const max = Math.max(...filas.map(f => f[1])), H = filas.length * fila + 4;
  const ancho = v => Math.max(2, (W - izq - der) * v / max);
  cont.innerHTML = `<svg width="${W}" height="${H}" role="img">` + filas.map((f, i) => {
    const y = i * fila + 4, w = ancho(f[1]);
    const nombre = f[0].length > maxC ? f[0].slice(0, maxC - 1) + "…" : f[0];
    return `<g data-tip="<b>${esc(f[0])}</b>${esc(etiqueta(f[1]))}${f[2] ? "<br>" + esc(f[2]) : ""}">
      <rect x="0" y="${y - 2}" width="${W}" height="${fila}" fill="transparent"/>
      <text x="${izq - 8}" y="${y + 13}" text-anchor="end">${esc(nombre)}</text>
      <path d="M${izq},${y + 3} h${w - 4} a4,4 0 0 1 4,4 v8 a4,4 0 0 1 -4,4 h${-(w - 4)} z" fill="${color}"/>
      <text x="${izq + w + 6}" y="${y + 13}" style="fill:var(--text-primary)">${esc(etiqueta(f[1]))}</text></g>`;
  }).join("") + "</svg>";
  enlazarTips(cont);
}

function lunes(s) { const d = new Date(s + "T00:00:00"); const k = (d.getDay() + 6) % 7; d.setDate(d.getDate() - k); return d.toISOString().slice(0,10); }
function semanal(facturas) {
  const cont = $("#gSemanal");
  const grupos = {};
  facturas.filter(f => f.fecha).forEach(f => { const s = lunes(f.fecha.slice(0,10));
    grupos[s] ??= { OK: 0, OBSERVADA: 0, RECHAZADA: 0, n: 0 }; grupos[s][f.estado] += f.monto || 0; grupos[s].n++; });
  const claves = Object.keys(grupos).sort(), semanas = [];
  if (claves.length) for (let d = new Date(claves[0] + "T00:00:00"); d.toISOString().slice(0,10) <= claves.at(-1); d.setDate(d.getDate() + 7)) {
    const k = d.toISOString().slice(0,10); grupos[k] ??= { OK: 0, OBSERVADA: 0, RECHAZADA: 0, n: 0 }; semanas.push(k); }
  if (!semanas.length) { cont.innerHTML = '<div class="vacio">Sin datos para el filtro</div>'; return; }
  const W = cont.clientWidth || 900, H = 240, izq = 64, abajo = 28, arriba = 8;
  const tot = s => grupos[s].OK + grupos[s].OBSERVADA + grupos[s].RECHAZADA;
  const bruto = Math.max(...semanas.map(tot)) || 1, mag = 10 ** Math.floor(Math.log10(bruto / 4));
  const pasoY = [1, 2, 2.5, 5, 10].map(m => m * mag).find(p => p * 4 >= bruto), max = pasoY * 4;
  const paso = (W - izq) / semanas.length, bw = Math.min(46, paso * 0.62);
  const y = v => arriba + (H - arriba - abajo) * (1 - v / max);
  let svg = `<svg width="${W}" height="${H}" role="img">`;
  for (let i = 0; i <= 4; i++) { const v = max * i / 4;
    svg += `<line x1="${izq}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${izq - 8}" y="${y(v) + 4}" text-anchor="end">${corto(v)}</text>`; }
  const colores = { OK: "var(--good)", OBSERVADA: "var(--warning)", RECHAZADA: "var(--critical)" };
  const cadaN = Math.ceil(semanas.length / Math.floor((W - izq) / 70));
  semanas.forEach((s, i) => {
    const g = grupos[s], x = izq + i * paso + (paso - bw) / 2;
    let base = 0, capas = "";
    const orden = ["OK", "OBSERVADA", "RECHAZADA"].filter(k => g[k] > 0);
    orden.forEach((k, j) => {
      const y0 = y(base), y1 = y(base + g[k]); const h = Math.max(1, y0 - y1 - (j < orden.length - 1 ? 2 : 0));
      const top = j === orden.length - 1;
      capas += top ? `<path d="M${x},${y0} v${-(h - 4)} a4,4 0 0 1 4,-4 h${bw - 8} a4,4 0 0 1 4,4 v${h - 4} z" fill="${colores[k]}"/>`
                   : `<rect x="${x}" y="${y0 - h}" width="${bw}" height="${h}" fill="${colores[k]}"/>`;
      base += g[k];
    });
    const t = `<b>Semana del ${fdate(s)}</b>Total ${fmt(tot(s))} · ${g.n} facturas<br>OK ${fmt(g.OK)}<br>Observada ${fmt(g.OBSERVADA)}<br>Rechazada ${fmt(g.RECHAZADA)}`;
    svg += `<g data-tip="${esc(t)}"><rect x="${izq + i * paso}" y="0" width="${paso}" height="${H - abajo}" fill="transparent"/>${capas}</g>`;
    if (i % cadaN === 0) svg += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${fdate(s).slice(0,5)}</text>`;
  });
  cont.innerHTML = svg + "</svg>";
  enlazarTips(cont);
}

function sumaPor(lista, clave, n = 12) {
  const m = {}; lista.forEach(x => { const k = x[clave] || "(sin dato)"; m[k] = (m[k] || 0) + (x.monto || 0); });
  const filas = Object.entries(m).sort((a, b) => b[1] - a[1]);
  if (filas.length > n) { const resto = filas.splice(n - 1).reduce((s, f) => s + f[1], 0); filas.push(["Otros", resto]); }
  return filas;
}

// ---------- tablas
function tabla(id, cols, filas, vacio = "Sin registros") {
  $(id).innerHTML = filas.length ? `<table><thead><tr>${cols.map(c => `<th${c[2] ? ' style="text-align:right"' : ""}>${c[0]}</th>`).join("")}</tr></thead><tbody>` +
    filas.map(f => "<tr>" + cols.map(c => `<td${c[2] ? ' class="n"' : ""}>${c[1](f)}</td>`).join("") + "</tr>").join("") + "</tbody></table>"
    : `<div class="vacio">${vacio}</div>`;
}

function render() {
  const fac = D.facturas.filter(pasa), hal = D.hallazgos.filter(pasa), arq = D.arqueos.filter(pasa), liq = D.liquidaciones.filter(pasa);
  const total = fac.reduce((s, f) => s + (f.monto || 0), 0);
  const rech = fac.filter(f => f.estado === "RECHAZADA").reduce((s, f) => s + (f.monto || 0), 0);
  const obs = fac.filter(f => f.estado === "OBSERVADA").reduce((s, f) => s + (f.monto || 0), 0);
  const alta = hal.filter(h => h.severidad === "ALTA" && h.estado === "Abierto").length;
  const dup = hal.filter(h => h.regla === "DUPLICADO_EXACTO");
  const sinValidar = hal.filter(h => h.severidad !== "BAJA" && !(S.vals[h.clave] || []).length).length;
  const faltante = arq.filter(a => a.diferencia < 0).reduce((s, a) => s + a.diferencia, 0);
  const kpi = (l, v, d = "") => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="d">${d}</div></div>`;
  $("#kpis").innerHTML = [
    kpi("Gasto presentado", corto(total), `${fac.length} facturas · ${liq.length} liquidaciones`),
    kpi("Monto rechazado", corto(rech), total ? `${(rech / total * 100).toFixed(1)}% del gasto` : ""),
    kpi("Monto observado", corto(obs), total ? `${(obs / total * 100).toFixed(1)}% del gasto` : ""),
    kpi("Hallazgos graves abiertos", alta, `${hal.length} hallazgos en total`),
    kpi("Duplicados detectados", dup.length, fmt(dup.reduce((s, h) => s + (h.monto || 0), 0)) + " en riesgo de doble pago"),
    kpi("Hallazgos sin validar", sinValidar, "ALTA y MEDIA pendientes de revisión"),
    kpi("Faltantes en arqueos", corto(faltante), `${arq.length} arqueos · ${arq.filter(a => a.diferencia < 0).length} con faltante`),
  ].join("");

  semanal(fac);
  barrasH("#gCategoria", sumaPor(fac, "categoria"));
  barrasH("#gCaja", sumaPor(fac, "caja"));
  barrasH("#gProveedor", sumaPor(fac, "proveedor", 10));
  const porRegla = {}; hal.filter(h => h.severidad !== "BAJA").forEach(h => { porRegla[h.titulo] = (porRegla[h.titulo] || 0) + 1; });
  barrasH("#gHallazgos", Object.entries(porRegla).sort((a, b) => b[1] - a[1]).slice(0, 12), "var(--series-1)", n => n + (n === 1 ? " hallazgo" : " hallazgos"), 300);

  const sev = $("#fSev").value, q = $("#fBuscar").value.toLowerCase();
  const orden = { ALTA: 0, MEDIA: 1, BAJA: 2 };
  const hs = hal.filter(h => (!sev || h.severidad === sev) && (!q || [h.titulo, h.detalle, h.proveedor, h.liquidacion, h.caja].join(" ").toLowerCase().includes(q)))
    .sort((a, b) => orden[a.severidad] - orden[b.severidad] || (b.fecha || "").localeCompare(a.fecha || ""));
  tabla("#tHallazgos", [
    ["Severidad", h => pill(h.severidad)], ["Caja", h => esc(h.caja)], ["Fecha", h => fdate(h.fecha)],
    ["Referencia", h => h.liquidacion ? `Liq. ${esc(h.liquidacion)}${h.fila ? " · fila " + h.fila : ""}` : esc(h.origen)],
    ["Proveedor", h => esc(h.proveedor)], ["Hallazgo", h => `<b>${esc(h.titulo)}</b><br><span class="sub">${esc(h.detalle)}</span>`],
    ["Monto", h => fmt(h.monto), true], ["Validación", celdaValidacion],
  ], hs, "Sin hallazgos para el filtro");

  tabla("#tDuplicados", [
    ["Tipo", h => pill(h.severidad) + " " + esc(h.titulo)], ["Caja", h => esc(h.caja)], ["Liquidación", h => esc(h.liquidacion)],
    ["Proveedor", h => esc(h.proveedor)], ["Detalle", h => esc(h.detalle)], ["Monto", h => fmt(h.monto), true], ["Validación", celdaValidacion],
  ], hal.filter(h => ["DUPLICADO_EXACTO", "POSIBLE_DUPLICADO", "PENDIENTE_YA_LIQUIDADO"].includes(h.regla))
        .sort((a, b) => orden[a.severidad] - orden[b.severidad]), "No se han detectado duplicados");

  const hoy = new Date(), dias = f => f ? Math.floor((hoy - new Date(f.slice(0,10) + "T00:00:00")) / 864e5) : null;
  const qu = $("#fUnidad").value.toLowerCase();
  const halPorCaja = {}; hal.filter(h => h.severidad === "ALTA").forEach(h => halPorCaja[h.caja] = (halPorCaja[h.caja] || 0) + 1);
  const uns = D.unidades.filter(u => (!F.caja || u.caja === F.caja) && (!qu || [u.caja, u.unidad, u.responsable].join(" ").toLowerCase().includes(qu)))
    .map(u => ({ ...u, dl: dias(u.ult_liq), alta: halPorCaja[u.caja] || 0 }))
    .sort((a, b) => (b.dl ?? 1e9) - (a.dl ?? 1e9) || b.alta - a.alta);
  const hace = n => n === 0 ? "Hoy" : `Hace ${n} ${n === 1 ? "día" : "días"}`;
  const entrega = u => !u.activa ? pill("INACTIVA") : u.dl == null ? '<span class="pill BAJA">SIN ENTREGAS</span>'
    : u.dl > 14 ? `<span class="pill ALTA">${hace(u.dl)}</span>` : u.dl > 7 ? `<span class="pill MEDIA">${hace(u.dl)}</span>` : `<span class="pill OK">${hace(u.dl)}</span>`;
  tabla("#tUnidades", [
    ["Código", u => esc(u.caja)], ["Unidad", u => esc(u.unidad)], ["Responsable", u => esc(u.responsable)],
    ["Última liquidación", entrega], ["Último arqueo", u => fdate(u.ult_arq)],
    ["Liquidaciones", u => u.n_liq, true], ["Hallazgos graves", u => u.alta, true], ["Fondo", u => fmt(u.fondo), true],
  ], uns, D.unidades.length ? "Sin unidades para el filtro" : "Cargue el catálogo de cajas en config/Catalogo_Cajas.xlsx");

  tabla("#tLiquidaciones", [
    ["Fecha", l => fdate(l.fecha)], ["Caja", l => esc(l.caja)], ["N°", l => esc(l.numero)], ["Custodio", l => esc(l.custodio)],
    ["Estado", l => pill(l.estado)], ["Facturas", l => `${l.n_facturas} <span class="sub">(${l.n_rechazadas} rech.)</span>`, true], ["Total", l => fmt(l.total), true],
  ], liq);

  tabla("#tArqueos", [
    ["Fecha", a => fdate(a.fecha)], ["Caja", a => esc(a.caja)], ["Realizado por", a => esc(a.realizado_por)],
    ["Estado", a => pill(a.estado)], ["Fondo", a => fmt(a.fondo), true], ["Diferencia", a => fmt(a.diferencia), true],
  ], arq);
}
// ================= registro de revisión, validaciones y bitácora
const ROLES = ["Revisor de liquidaciones", "Validador de evidencia", "Jefatura / aprobador", "Auditoría interna", "Consulta"];
const MOTIVOS = ["Revisión semanal de liquidaciones", "Validación de evidencia de hallazgos", "Confirmar que la información está al día",
  "Seguimiento de hallazgos abiertos", "Consulta general"];
const RESULTADOS = { CONFIRMADO: "Incumplimiento confirmado", JUSTIFICADO: "Justificado: se acepta",
  INFO: "Requiere más información", FALSO: "Falso positivo" };
const VIGENCIA = { AL_DIA: "Al día", DESACTUALIZADA: "Faltan entregas recientes", INCONSISTENTE: "Datos inconsistentes" };
const TIPOS = { ingreso: "Ingreso", vigencia: "Confirmación de vigencia", validacion: "Validación de evidencia" };
const S = { U: null, DB: null, me: null, admin: false, sesion: null, vals: {}, eventosVal: [], perfiles: {}, bitacora: [], downloads: null };
const mesActual = () => new Date().toISOString().slice(0, 7);
const fh = s => { try { return new Date(s).toLocaleString("es-CR", { dateStyle: "short", timeStyle: "short" }); } catch (e) { return s; } };
const nombre = uid => (S.perfiles[uid] && S.perfiles[uid].name) || "Persona sin nombre visible";
const porClave = Object.fromEntries(D.hallazgos.map(h => [h.clave, h]));
document.querySelectorAll(".corte").forEach(el => el.textContent = D.generado);
$("#rRol").innerHTML = ROLES.map(r => `<option>${esc(r)}</option>`).join("");
$("#rMotivo").innerHTML = MOTIVOS.map(r => `<option>${esc(r)}</option>`).join("");
$("#valOpciones").innerHTML = Object.entries(RESULTADOS).map(([k, v]) => `<label><input type="radio" name="res" value="${k}" required> ${esc(v)}</label>`).join("");

function celdaValidacion(h) {
  const v = (S.vals[h.clave] || [])[0];
  const estado = v ? `<span class="pill V-${esc(v.resultado)}">${esc(RESULTADOS[v.resultado] || v.resultado)}</span>
    <div class="sub">${esc(nombre(v.uid))} · ${esc(fh(v.ts))}</div>` : '<span class="sub">Sin validar</span>';
  return estado + `<button class="btn-link" type="button" data-validar="${esc(h.clave)}">${v ? "Actualizar validación" : "Validar"}</button>`;
}

function bloquear(titulo, texto) {
  $("#puertaCargando").hidden = true; $("#puertaForm").hidden = true; $("#puertaAviso").hidden = false;
  $("#avisoTitulo").textContent = titulo; $("#avisoTexto").textContent = texto;
  $("#app").hidden = true; $("#puerta").hidden = false;
}

async function anexar(ruta, evento) {
  // Un documento por persona y mes: evita llenar la base con un documento por evento.
  const ref = S.DB.doc(ruta + "/meses/" + mesActual());
  const snap = await ref.get();
  const eventos = snap.exists ? [...(snap.data().eventos || [])] : [];
  eventos.push(evento);
  await ref.set({ eventos });
  await S.DB.doc(ruta).set({ ultimo: evento.ts });
}

async function iniciar() {
  if (!window.claude || !window.claude.use) return bloquear("Abra el dashboard desde su enlace oficial",
    "Esta copia no puede registrar su ingreso. Use el enlace de claude.ai que le compartió el administrador: ahí cada revisión queda registrada.");
  const [U, DB] = await Promise.all([claude.use("user"), claude.use("db")]);
  if (!U || !DB) return bloquear("No se pudo verificar su identidad",
    "El registro de revisión no está disponible en esta vista. Abra el enlace oficial con la cuenta de su organización.");
  const me = await U.me();
  if (!me.id) return bloquear("Inicie sesión para continuar",
    "Cada persona que revisa el dashboard debe quedar identificada. Inicie sesión con la cuenta de su organización y abra de nuevo el enlace.");
  Object.assign(S, { U, DB, me, admin: me.canEdit || me.isOwner });
  $("#idNombre").textContent = me.name || "Su cuenta";
  $("#idCorreo").textContent = me.email || "";
  $("#idAvatar").src = me.avatarUrl;
  $("#puertaCargando").hidden = true; $("#puertaForm").hidden = false;
  claude.use("downloads").then(d => { S.downloads = d; $("#bDescargar").hidden = !d; });
}

$("#puertaForm").addEventListener("submit", async e => {
  e.preventDefault();
  const ev = { tipo: "ingreso", ts: new Date().toISOString(), rol: $("#rRol").value, motivo: $("#rMotivo").value,
               alcance: $("#rAlcance").value.trim().slice(0, 200), corte: D.generado };
  $("#puertaBtn").disabled = true; $("#puertaError").hidden = true;
  try {
    await anexar("accesos/" + S.me.id, ev);
  } catch (err) {
    $("#puertaBtn").disabled = false;
    if (err && err.code === "invalid_argument") return bloquear("Su acceso no permite registrar la revisión",
      "Para ver el dashboard su ingreso debe quedar registrado. Pida al administrador que le comparta el dashboard con permiso de Colaborador.");
    $("#puertaError").textContent = "No se pudo registrar su ingreso. Revise su conexión e intente de nuevo.";
    $("#puertaError").hidden = false;
    return;
  }
  S.sesion = ev;
  $("#sesionTexto").innerHTML = `Sesión registrada: <b>${esc(S.me.name || "Su cuenta")}</b> · ${esc(ev.rol)} · ${esc(ev.motivo)} · ${esc(fh(ev.ts))}`;
  $("#puerta").hidden = true; $("#app").hidden = false;
  $("#bitacora").hidden = !S.admin;
  render();
  await cargarValidaciones();
  if (S.admin) cargarBitacora();
});

async function leerEventos(raiz) {
  const personas = await S.DB.collection(raiz).get();
  const eventos = [];
  await Promise.all(personas.docs.map(async p => {
    const meses = await S.DB.collection(raiz + "/" + p.id + "/meses").get();
    meses.docs.forEach(m => (m.data().eventos || []).forEach(ev => eventos.push({ ...ev, uid: p.id })));
  }));
  return eventos.sort((a, b) => (b.ts || "").localeCompare(a.ts || ""));
}

async function cargarValidaciones() {
  try {
    S.eventosVal = await leerEventos("validaciones");
    S.vals = {};
    S.eventosVal.forEach(v => (S.vals[v.clave] ??= []).push(v));
    S.perfiles = { ...S.perfiles, ...(await S.U.profiles([...new Set(S.eventosVal.map(v => v.uid))])) };
    render();
  } catch (err) { console.warn("No se pudieron leer las validaciones", err); }
}

// ---- validar un hallazgo
let hallazgoActual = null;
document.addEventListener("click", e => {
  const b = e.target.closest("[data-validar]");
  if (!b || !S.sesion) return;
  hallazgoActual = porClave[b.dataset.validar];
  if (!hallazgoActual) return;
  const h = hallazgoActual;
  $("#valResumen").innerHTML = `${pill(h.severidad)} <b>${esc(h.titulo)}</b><br>${esc(h.caja)}${h.liquidacion ? " · Liq. " + esc(h.liquidacion) : ""}${h.fila ? " · fila " + h.fila : ""}${h.proveedor ? " · " + esc(h.proveedor) : ""}<br><span class="sub">${esc(h.detalle)}</span>`;
  $("#valForm").reset(); $("#valError").hidden = true; $("#dlgValidar").hidden = false;
  $("#valComentario").focus();
});
$("#valCancelar").onclick = () => { $("#dlgValidar").hidden = true; };
$("#valForm").addEventListener("submit", async e => {
  e.preventDefault();
  const h = hallazgoActual, res = new FormData(e.target).get("res"), comentario = $("#valComentario").value.trim();
  if (comentario.length < 10) { $("#valError").textContent = "Describa la evidencia revisada (al menos 10 caracteres)."; $("#valError").hidden = false; return; }
  const ev = { tipo: "validacion", ts: new Date().toISOString(), clave: h.clave, resultado: res, comentario, rol: S.sesion.rol,
               corte: D.generado, caja: h.caja, regla: h.regla, liquidacion: h.liquidacion || "", fila: h.fila || null };
  $("#valBtn").disabled = true;
  try {
    await anexar("validaciones/" + S.me.id, ev);
    $("#dlgValidar").hidden = true;
    await cargarValidaciones();
    if (S.admin) cargarBitacora();
  } catch (err) {
    $("#valError").textContent = err && err.code === "invalid_argument"
      ? "Su acceso no permite registrar validaciones. Pida permiso de Colaborador al administrador."
      : "No se pudo registrar la validación. Intente de nuevo.";
    $("#valError").hidden = false;
  } finally { $("#valBtn").disabled = false; }
});

// ---- confirmar vigencia
$("#vigAbrir").onclick = () => { $("#vigForm").reset(); $("#vigError").hidden = true; $("#dlgVigencia").hidden = false; };
$("#vigCancelar").onclick = () => { $("#dlgVigencia").hidden = true; };
$("#vigForm").addEventListener("submit", async e => {
  e.preventDefault();
  const res = new FormData(e.target).get("vig"), comentario = $("#vigComentario").value.trim();
  if (res !== "AL_DIA" && comentario.length < 10) { $("#vigError").textContent = "Indique qué falta o qué no coincide."; $("#vigError").hidden = false; return; }
  $("#vigBtn").disabled = true;
  try {
    await anexar("accesos/" + S.me.id, { tipo: "vigencia", ts: new Date().toISOString(), resultado: res, comentario,
                                         rol: S.sesion.rol, corte: D.generado });
    $("#dlgVigencia").hidden = true;
    $("#vigAbrir").textContent = "Confirmación registrada · " + VIGENCIA[res];
    if (S.admin) cargarBitacora();
  } catch (err) {
    $("#vigError").textContent = "No se pudo registrar la confirmación. Intente de nuevo."; $("#vigError").hidden = false;
  } finally { $("#vigBtn").disabled = false; }
});

// ---- bitácora (administrador y editores)
async function cargarBitacora() {
  $("#bEstado").textContent = "Cargando bitácora…";
  try {
    const accesos = await leerEventos("accesos");
    S.bitacora = [...accesos, ...S.eventosVal].sort((a, b) => (b.ts || "").localeCompare(a.ts || ""));
    S.perfiles = { ...S.perfiles, ...(await S.U.profiles([...new Set(S.bitacora.map(v => v.uid))])) };
    $("#bEstado").textContent = `${S.bitacora.length} registros de ${new Set(S.bitacora.map(v => v.uid)).size} personas.`;
    renderBitacora();
  } catch (err) { $("#bEstado").textContent = "No se pudo leer la bitácora. Use Actualizar para reintentar."; }
}
function detalleEvento(v) {
  if (v.tipo === "ingreso") return [v.motivo, v.alcance && "Alcance: " + v.alcance].filter(Boolean).join(" · ");
  if (v.tipo === "vigencia") return [VIGENCIA[v.resultado] || v.resultado, v.comentario].filter(Boolean).join(" · ");
  return `${RESULTADOS[v.resultado] || v.resultado} · ${v.caja}${v.liquidacion ? " Liq. " + v.liquidacion : ""}${v.fila ? " fila " + v.fila : ""} · ${(porClave[v.clave] || {}).titulo || v.regla} · ${v.comentario}`;
}
function filasBitacora() {
  const t = $("#bTipo").value, q = $("#bBuscar").value.toLowerCase();
  return S.bitacora.filter(v => (!t || v.tipo === t) &&
    (!q || [nombre(v.uid), v.rol, detalleEvento(v)].join(" ").toLowerCase().includes(q)));
}
function renderBitacora() {
  tabla("#tBitacora", [
    ["Fecha y hora", v => esc(fh(v.ts))], ["Persona", v => `<b>${esc(nombre(v.uid))}</b>`],
    ["Registro", v => `<span class="pill T-${esc(v.tipo)}">${esc(TIPOS[v.tipo] || v.tipo)}</span>`], ["Rol", v => esc(v.rol)],
    ["Detalle", v => esc(detalleEvento(v))], ["Corte revisado", v => esc(v.corte)],
  ], filasBitacora(), "Sin registros para el filtro");
}
$("#bTipo").onchange = renderBitacora; $("#bBuscar").oninput = renderBitacora;
$("#bActualizar").onclick = async () => { await cargarValidaciones(); await cargarBitacora(); };
$("#bDescargar").onclick = async () => {
  const q = s => `"${String(s ?? "").replace(/"/g, '""')}"`;
  const filas = [["Fecha y hora", "Persona", "Registro", "Rol", "Detalle", "Corte revisado"].map(q).join(",")]
    .concat(filasBitacora().map(v => [v.ts, nombre(v.uid), TIPOS[v.tipo] || v.tipo, v.rol, detalleEvento(v), v.corte].map(q).join(",")));
  try {
    await S.downloads.save({ filename: `Bitacora_Revision_CajaChica_${new Date().toISOString().slice(0, 10)}.csv`, data: "\ufeff" + filas.join("\r\n") });
  } catch (err) {
    if (err && err.code !== "declined") $("#bEstado").textContent = "No se pudo generar la descarga en esta vista.";
  }
};

iniciar();
addEventListener("resize", () => { clearTimeout(window._r); window._r = setTimeout(render, 150); });
</script>
"""
