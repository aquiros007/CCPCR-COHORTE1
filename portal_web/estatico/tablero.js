"use strict";
(function () {
  const raiz = document.getElementById("tablero");
  if (!raiz) return;
  const CSRF = raiz.dataset.csrf;
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = n => n == null ? "—" : (n < 0 ? "−" : "") + "₡" + Math.abs(Math.round(n)).toLocaleString("es-CR");
  const corto = n => { const a = Math.abs(n), s = n < 0 ? "−" : ""; return s + (a >= 1e6 ? "₡" + (a / 1e6).toFixed(1) + " M" : a >= 1e3 ? "₡" + Math.round(a / 1e3) + " k" : "₡" + Math.round(a)); };
  const fdate = s => s ? String(s).slice(0, 10).split("-").reverse().join("/") : "—";
  const fh = s => { try { return new Date(s).toLocaleString("es-CR", { dateStyle: "short", timeStyle: "short" }); } catch (e) { return s; } };
  const CLASE = { ALTA: "critico", MEDIA: "alerta", BAJA: "", OK: "bien", OBSERVADA: "alerta", RECHAZADA: "critico", APROBABLE: "bien",
    "CON RECHAZOS": "critico", "CON OBSERVACIONES": "alerta", "CON HALLAZGOS GRAVES": "critico", CUADRADO: "bien",
    "LISTO PARA APROBACIÓN": "bien", "CON DIFERENCIAS": "critico", "REVISIÓN MANUAL": "alerta", INCOMPLETO: "alerta",
    CONFIRMADO: "critico", JUSTIFICADO: "bien", FALSO: "bien", INFO: "alerta" };
  const pill = (s, texto) => `<span class="pill ${CLASE[s] || ""}">${esc(texto || s)}</span>`;

  let D = null, VALS = {}, REGISTRO = [], RES = {}, VIG = {};
  const F = { caja: "", desde: "", hasta: "" };

  async function cargar() {
    const r = await fetch("/admin/tablero/datos.json", { credentials: "same-origin" });
    if (!r.ok) return;
    const j = await r.json();
    RES = j.resultados; VIG = j.vigencia;
    VALS = {};
    j.validaciones.forEach(v => (VALS[v.clave] ??= []).push(v));
    REGISTRO = [...j.validaciones.map(v => ({ ...v, tipo: "validacion" })), ...j.vigencias.map(v => ({ ...v, tipo: "vigencia" }))]
      .sort((a, b) => (b.ts || "").localeCompare(a.ts || ""));
    if (!j.datos) return;
    D = j.datos;
    $("#gen").textContent = D.generado || "—";
    $("#aviso").innerHTML = D.aviso ? `<span class="aviso-demo">${esc(D.aviso)}</span>` : "";
    prepararFiltros();
    render();
  }

  // ---------------------------------------------------------------- filtros
  function prepararFiltros() {
    if ($("#fCaja").options.length) return;
    const cajas = [...new Set([...(D.unidades || []), ...D.facturas, ...D.arqueos].map(x => x.caja))].sort();
    const nombre = Object.fromEntries((D.unidades || []).map(u => [u.caja, u.unidad]));
    $("#fCaja").innerHTML = `<option value="">Todas (${cajas.length})</option>` +
      cajas.map(c => `<option value="${esc(c)}">${esc(c)}${nombre[c] ? " · " + esc(nombre[c]) : ""}</option>`).join("");
    const cambiar = () => { F.caja = $("#fCaja").value; F.desde = $("#fDesde").value; F.hasta = $("#fHasta").value; render(); };
    ["#fCaja", "#fDesde", "#fHasta"].forEach(s => $(s).addEventListener("change", () => {
      document.querySelectorAll("#rangos button").forEach(b => b.classList.remove("on")); cambiar(); }));
    document.querySelectorAll("#rangos button").forEach(b => b.addEventListener("click", () => {
      document.querySelectorAll("#rangos button").forEach(x => x.classList.toggle("on", x === b));
      const d = +b.dataset.d;
      $("#fHasta").value = ""; $("#fDesde").value = d ? new Date(Date.now() - d * 864e5).toISOString().slice(0, 10) : "";
      cambiar();
    }));
    ["#fSev", "#fVal"].forEach(s => $(s).addEventListener("change", render));
    ["#fBuscar", "#fUnidad"].forEach(s => $(s).addEventListener("input", render));
  }
  const pasa = x => (!F.caja || x.caja === F.caja) && (!F.desde || (x.fecha || "") >= F.desde) && (!F.hasta || (x.fecha || "") <= F.hasta);

  // ---------------------------------------------------------------- tooltip
  const tip = $("#tip");
  function enlazarTips(cont) {
    cont.querySelectorAll("[data-tip]").forEach(el => {
      el.addEventListener("mousemove", e => {
        tip.innerHTML = el.dataset.tip; tip.hidden = false;
        tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px";
        tip.style.top = (e.clientY + 14) + "px";
      });
      el.addEventListener("mouseleave", () => { tip.hidden = true; });
    });
  }

  // ---------------------------------------------------------------- gráficos
  function barrasH(id, filas, etiqueta = fmt, izqMax = 190) {
    const cont = $(id);
    if (!filas.length) { cont.innerHTML = '<div class="vacio">Sin datos para el filtro</div>'; return; }
    const W = cont.clientWidth || 500, alto = 26, izq = Math.min(izqMax, W * 0.45), der = 84, maxC = Math.floor((izq - 12) / 6);
    const max = Math.max(...filas.map(f => f[1])) || 1, H = filas.length * alto + 4;
    const ancho = v => Math.max(2, (W - izq - der) * v / max);
    cont.innerHTML = `<svg width="${W}" height="${H}" role="img">` + filas.map((f, i) => {
      const y = i * alto + 4, w = ancho(f[1]), nombre = f[0].length > maxC ? f[0].slice(0, maxC - 1) + "…" : f[0];
      return `<g data-tip="${esc(`<b>${esc(f[0])}</b>${esc(etiqueta(f[1]))}`)}">
        <rect x="0" y="${y - 2}" width="${W}" height="${alto}" fill="transparent"/>
        <text x="${izq - 8}" y="${y + 13}" text-anchor="end">${esc(nombre)}</text>
        <path d="M${izq},${y + 3} h${Math.max(0, w - 4)} a4,4 0 0 1 4,4 v8 a4,4 0 0 1 -4,4 h${-Math.max(0, w - 4)} z" fill="var(--serie)"/>
        <text class="valor" x="${izq + w + 6}" y="${y + 13}">${esc(etiqueta(f[1]))}</text></g>`;
    }).join("") + "</svg>";
    enlazarTips(cont);
  }

  const lunes = s => { const d = new Date(s + "T00:00:00"); d.setDate(d.getDate() - (d.getDay() + 6) % 7); return d.toISOString().slice(0, 10); };
  function semanal(facturas) {
    const cont = $("#gSemanal"), grupos = {};
    const vacio = () => ({ OK: 0, OBSERVADA: 0, RECHAZADA: 0, n: 0 });
    facturas.filter(f => f.fecha).forEach(f => { const s = lunes(String(f.fecha).slice(0, 10)); grupos[s] ??= vacio();
      grupos[s][f.estado] = (grupos[s][f.estado] || 0) + (f.monto || 0); grupos[s].n++; });
    const claves = Object.keys(grupos).sort(), semanas = [];
    if (claves.length) for (let d = new Date(claves[0] + "T00:00:00"); d.toISOString().slice(0, 10) <= claves.at(-1); d.setDate(d.getDate() + 7)) {
      const k = d.toISOString().slice(0, 10); grupos[k] ??= vacio(); semanas.push(k); }
    if (!semanas.length) { cont.innerHTML = '<div class="vacio">Sin datos para el filtro</div>'; return; }
    const W = cont.clientWidth || 900, H = 240, izq = 64, abajo = 28, arriba = 8;
    const tot = s => grupos[s].OK + grupos[s].OBSERVADA + grupos[s].RECHAZADA;
    const bruto = Math.max(...semanas.map(tot)) || 1, mag = 10 ** Math.floor(Math.log10(bruto / 4));
    const pasoY = [1, 2, 2.5, 5, 10].map(m => m * mag).find(p => p * 4 >= bruto), max = pasoY * 4;
    const paso = (W - izq) / semanas.length, bw = Math.min(46, paso * 0.62), y = v => arriba + (H - arriba - abajo) * (1 - v / max);
    const colores = { OK: "var(--bien)", OBSERVADA: "var(--alerta)", RECHAZADA: "var(--critico)" };
    let svg = `<svg width="${W}" height="${H}" role="img">`;
    for (let i = 0; i <= 4; i++) { const v = max * i / 4;
      svg += `<line class="linea-guia" x1="${izq}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><text x="${izq - 8}" y="${y(v) + 4}" text-anchor="end">${corto(v)}</text>`; }
    const cadaN = Math.max(1, Math.ceil(semanas.length / Math.max(1, Math.floor((W - izq) / 70))));
    semanas.forEach((s, i) => {
      const g = grupos[s], x = izq + i * paso + (paso - bw) / 2, orden = ["OK", "OBSERVADA", "RECHAZADA"].filter(k => g[k] > 0);
      let base = 0, capas = "";
      orden.forEach((k, j) => {
        const y0 = y(base), y1 = y(base + g[k]), h = Math.max(1, y0 - y1 - (j < orden.length - 1 ? 2 : 0));
        capas += j === orden.length - 1
          ? `<path d="M${x},${y0} v${-Math.max(0, h - 4)} a4,4 0 0 1 4,-4 h${bw - 8} a4,4 0 0 1 4,4 v${Math.max(0, h - 4)} z" fill="${colores[k]}"/>`
          : `<rect x="${x}" y="${y0 - h}" width="${bw}" height="${h}" fill="${colores[k]}"/>`;
        base += g[k];
      });
      const t = `<b>Semana del ${fdate(s)}</b>Total ${fmt(tot(s))} · ${g.n} facturas<br>OK ${fmt(g.OK)}<br>Observada ${fmt(g.OBSERVADA)}<br>Rechazada ${fmt(g.RECHAZADA)}`;
      svg += `<g data-tip="${esc(t)}"><rect x="${izq + i * paso}" y="0" width="${paso}" height="${H - abajo}" fill="transparent"/>${capas}</g>`;
      if (i % cadaN === 0) svg += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${fdate(s).slice(0, 5)}</text>`;
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

  // ---------------------------------------------------------------- tablas
  function tabla(id, cols, filas, vacio = "Sin registros") {
    $(id).innerHTML = filas.length ? `<table><thead><tr>${cols.map(c => `<th${c[2] ? ' class="n"' : ""}>${c[0]}</th>`).join("")}</tr></thead><tbody>` +
      filas.map(f => "<tr>" + cols.map(c => `<td${c[2] ? ' class="n"' : ""}>${c[1](f)}</td>`).join("") + "</tr>").join("") + "</tbody></table>"
      : `<div class="vacio">${vacio}</div>`;
  }

  function celdaValidacion(h) {
    const v = (VALS[h.clave] || [])[0];
    return (v ? `${pill(v.resultado, RES[v.resultado])}<div class="sub">${esc(v.actor)} · ${esc(fh(v.ts))}</div>` : '<span class="sub">Sin validar</span>')
      + `<div><button class="enlace" type="button" data-validar="${esc(h.clave)}">${v ? "Actualizar validación" : "Validar"}</button></div>`;
  }

  function render() {
    if (!D) return;
    const fac = D.facturas.filter(pasa), hal = D.hallazgos.filter(pasa), arq = D.arqueos.filter(pasa), liq = D.liquidaciones.filter(pasa);
    const total = fac.reduce((s, f) => s + (f.monto || 0), 0);
    const suma = est => fac.filter(f => f.estado === est).reduce((s, f) => s + (f.monto || 0), 0);
    const rech = suma("RECHAZADA"), obs = suma("OBSERVADA");
    const dup = hal.filter(h => h.regla === "DUPLICADO_EXACTO");
    const sinVal = hal.filter(h => h.severidad !== "BAJA" && !(VALS[h.clave] || []).length).length;
    const faltante = arq.filter(a => a.diferencia < 0).reduce((s, a) => s + a.diferencia, 0);
    const kpi = (l, v, d = "") => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="d">${d}</div></div>`;
    $("#kpis").innerHTML = [
      kpi("Gasto presentado", corto(total), `${fac.length} facturas · ${liq.length} liquidaciones`),
      kpi("Monto rechazado", corto(rech), total ? `${(rech / total * 100).toFixed(1)}% del gasto` : ""),
      kpi("Monto observado", corto(obs), total ? `${(obs / total * 100).toFixed(1)}% del gasto` : ""),
      kpi("Hallazgos graves", hal.filter(h => h.severidad === "ALTA").length, `${hal.length} hallazgos en total`),
      kpi("Hallazgos sin validar", sinVal, "ALTA y MEDIA pendientes de revisión"),
      kpi("Duplicados detectados", dup.length, fmt(dup.reduce((s, h) => s + (h.monto || 0), 0)) + " en riesgo"),
      kpi("Faltantes en arqueos", corto(faltante), `${arq.length} arqueos · ${arq.filter(a => a.diferencia < 0).length} con faltante`),
    ].join("");

    semanal(fac);
    barrasH("#gCategoria", sumaPor(fac, "categoria"));
    barrasH("#gCaja", sumaPor(fac, "caja"));
    barrasH("#gProveedor", sumaPor(fac, "proveedor", 10));
    const porRegla = {}; hal.filter(h => h.severidad !== "BAJA").forEach(h => { porRegla[h.titulo] = (porRegla[h.titulo] || 0) + 1; });
    barrasH("#gHallazgos", Object.entries(porRegla).sort((a, b) => b[1] - a[1]).slice(0, 12), n => n + (n === 1 ? " hallazgo" : " hallazgos"), 300);

    const sev = $("#fSev").value, fv = $("#fVal").value, q = $("#fBuscar").value.toLowerCase(), orden = { ALTA: 0, MEDIA: 1, BAJA: 2 };
    const hs = hal.filter(h => (!sev || h.severidad === sev)
        && (!fv || (fv === "si") === Boolean((VALS[h.clave] || []).length))
        && (!q || [h.titulo, h.detalle, h.proveedor, h.liquidacion, h.caja].join(" ").toLowerCase().includes(q)))
      .sort((a, b) => orden[a.severidad] - orden[b.severidad] || (b.fecha || "").localeCompare(a.fecha || ""));
    tabla("#tHallazgos", [
      ["Prioridad", h => pill(h.severidad)], ["Caja", h => esc(h.caja)], ["Fecha", h => fdate(h.fecha)],
      ["Referencia", h => h.liquidacion ? `Liq. ${esc(h.liquidacion)}${h.fila ? " · fila " + h.fila : ""}` : esc(h.origen)],
      ["Proveedor", h => esc(h.proveedor)], ["Hallazgo", h => `<b>${esc(h.titulo)}</b><div class="sub">${esc(h.detalle)}</div>`],
      ["Monto", h => fmt(h.monto), true], ["Validación", celdaValidacion],
    ], hs, "Sin hallazgos para el filtro");

    tabla("#tDuplicados", [
      ["Tipo", h => pill(h.severidad) + " " + esc(h.titulo)], ["Caja", h => esc(h.caja)], ["Liquidación", h => esc(h.liquidacion)],
      ["Proveedor", h => esc(h.proveedor)], ["Detalle", h => esc(h.detalle)], ["Monto", h => fmt(h.monto), true], ["Validación", celdaValidacion],
    ], hal.filter(h => ["DUPLICADO_EXACTO", "POSIBLE_DUPLICADO", "PENDIENTE_YA_LIQUIDADO"].includes(h.regla)), "No se han detectado duplicados");

    const hoy = new Date(), dias = f => f ? Math.floor((hoy - new Date(String(f).slice(0, 10) + "T00:00:00")) / 864e5) : null;
    const qu = $("#fUnidad").value.toLowerCase(), graves = {};
    hal.filter(h => h.severidad === "ALTA").forEach(h => graves[h.caja] = (graves[h.caja] || 0) + 1);
    const hace = n => n === 0 ? "Hoy" : `Hace ${n} ${n === 1 ? "día" : "días"}`;
    const entrega = u => !u.activa ? pill("ALTA", "Inactiva") : u.dl == null ? pill("BAJA", "Sin entregas")
      : pill(u.dl > 14 ? "ALTA" : u.dl > 7 ? "MEDIA" : "OK", hace(u.dl));
    tabla("#tUnidades", [
      ["FUC", u => esc(u.caja)], ["Unidad", u => esc(u.unidad)], ["Persona encargada", u => esc(u.responsable)],
      ["Última liquidación", entrega], ["Último arqueo", u => fdate(u.ult_arq)], ["Liquidaciones", u => u.n_liq, true],
      ["Hallazgos graves", u => u.alta, true], ["Fondo", u => fmt(u.fondo), true],
    ], (D.unidades || []).filter(u => (!F.caja || u.caja === F.caja) && (!qu || [u.caja, u.unidad, u.responsable].join(" ").toLowerCase().includes(qu)))
      .map(u => ({ ...u, dl: dias(u.ult_liq), alta: graves[u.caja] || 0 })).sort((a, b) => (b.dl ?? 1e9) - (a.dl ?? 1e9) || b.alta - a.alta),
      "No hay unidades en el catálogo");

    tabla("#tLiquidaciones", [
      ["Fecha", l => fdate(l.fecha)], ["Caja", l => esc(l.caja)], ["N.º", l => esc(l.numero)], ["Persona encargada", l => esc(l.custodio)],
      ["Estado", l => pill(l.estado)], ["Facturas", l => `${l.n_facturas} <span class="sub">(${l.n_rechazadas} rech.)</span>`, true], ["Total", l => fmt(l.total), true],
    ], liq);
    tabla("#tArqueos", [
      ["Fecha", a => fdate(a.fecha)], ["Caja", a => esc(a.caja)], ["Realizado por", a => esc(a.realizado_por)],
      ["Estado", a => pill(a.estado)], ["Fondo", a => fmt(a.fondo), true], ["Diferencia", a => fmt(a.diferencia), true],
    ], arq);
    tabla("#tComprobantes", [
      ["Cruce", c => pill(c.estado)], ["Proveedor", c => `<b>${esc(c.proveedor)}</b><div class="sub">${esc(c.cedula)}</div>`],
      ["Factura", c => `${esc(c.consecutivo || "—")}<div class="sub">${fdate(c.fecha)}</div>`], ["Hacienda", c => esc(c.hacienda)],
      ["Controles", c => { const no = (c.controles || []).filter(x => x.estado !== "CUMPLE");
        return no.length ? no.map(x => `<div class="sub">✗ ${esc(x.control)}${x.detalle ? " · " + esc(x.detalle) : ""}</div>`).join("") : '<span class="sub">Todos cumplen</span>'; }],
      ["Total", c => fmt(c.total), true],
    ], (D.comprobantes || []).filter(c => !F.caja || !c.caja || c.caja === F.caja), "No hay comprobantes cruzados");
    tabla("#tRegistro", [
      ["Fecha y hora", r => esc(fh(r.ts))], ["Persona", r => esc(r.actor)], ["Rol", r => esc(r.rol)],
      ["Registro", r => r.tipo === "validacion" ? pill(r.resultado, "Validación: " + (RES[r.resultado] || r.resultado)) : pill(r.resultado === "AL_DIA" ? "OK" : "MEDIA", "Vigencia: " + (VIG[r.resultado] || r.resultado))],
      ["Detalle", r => esc(r.tipo === "validacion" ? `${r.caja || ""} ${r.liquidacion ? "Liq. " + r.liquidacion : ""} ${r.fila ? "fila " + r.fila : ""} · ${r.regla || ""} · ${r.comentario || ""}` : (r.comentario || ""))],
      ["Corte", r => esc(r.corte)],
    ], REGISTRO.slice(0, 50), "Todavía no hay validaciones ni confirmaciones");
  }

  // ---------------------------------------------------------------- envíos al servidor
  async function enviar(url, cuerpo) {
    const r = await fetch(url, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF }, body: JSON.stringify(cuerpo) });
    if (!r.ok) { let m = "No se pudo registrar. Intente de nuevo."; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  }

  let actual = null;
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-validar]");
    if (!b || !D) return;
    actual = D.hallazgos.find(h => h.clave === b.dataset.validar);
    if (!actual) return;
    const h = actual;
    $("#valResumen").innerHTML = `${pill(h.severidad)} <b>${esc(h.titulo)}</b><br>${esc(h.caja)}${h.liquidacion ? " · Liq. " + esc(h.liquidacion) : ""}${h.fila ? " · fila " + h.fila : ""}${h.proveedor ? " · " + esc(h.proveedor) : ""}<div class="sub">${esc(h.detalle)}</div>`;
    $("#valOpciones").innerHTML = "<legend>Resultado</legend>" + Object.entries(RES).map(([k, v]) => `<label><input type="radio" name="res" value="${k}" required> ${esc(v)}</label>`).join("");
    $("#valForm").reset(); $("#valError").hidden = true; $("#dlgValidar").hidden = false; $("#valComentario").focus();
  });
  $("#valCancelar").addEventListener("click", () => { $("#dlgValidar").hidden = true; });
  $("#valForm").addEventListener("submit", async e => {
    e.preventDefault();
    const h = actual, res = new FormData(e.target).get("res");
    $("#valBtn").disabled = true;
    try {
      await enviar("/admin/tablero/validar", { clave: h.clave, resultado: res, comentario: $("#valComentario").value,
        caja: h.caja, regla: h.regla, liquidacion: h.liquidacion || "", fila: h.fila || null });
      $("#dlgValidar").hidden = true; await cargar();
    } catch (err) { $("#valError").textContent = err.message; $("#valError").hidden = false; }
    finally { $("#valBtn").disabled = false; }
  });

  $("#vigAbrir").addEventListener("click", () => {
    $("#vigOpciones").innerHTML = "<legend>Resultado</legend>" + Object.entries(VIG).map(([k, v]) => `<label><input type="radio" name="vig" value="${k}" required> ${esc(v)}</label>`).join("");
    $("#vigForm").reset(); $("#vigError").hidden = true; $("#dlgVigencia").hidden = false;
  });
  $("#vigCancelar").addEventListener("click", () => { $("#dlgVigencia").hidden = true; });
  $("#vigForm").addEventListener("submit", async e => {
    e.preventDefault();
    $("#vigBtn").disabled = true;
    try {
      await enviar("/admin/tablero/vigencia", { resultado: new FormData(e.target).get("vig"), comentario: $("#vigComentario").value });
      $("#dlgVigencia").hidden = true; $("#vigAbrir").textContent = "Confirmación registrada"; await cargar();
    } catch (err) { $("#vigError").textContent = err.message; $("#vigError").hidden = false; }
    finally { $("#vigBtn").disabled = false; }
  });

  addEventListener("resize", () => { clearTimeout(window._r); window._r = setTimeout(render, 150); });
  cargar();
})();
