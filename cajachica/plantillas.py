"""Plantillas para las personas encargadas y los proveedores, y datos de demostración."""
import csv
import random
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .util import solo_digitos

AZUL = "1F3A5F"
COLUMNAS_FACTURAS = ["Fecha factura", "Tipo documento", "Clave numérica", "Número de factura", "Proveedor",
                     "Cédula proveedor", "Receptor (a nombre de)", "Cédula receptor", "Descripción del gasto",
                     "Categoría", "Subtotal", "IVA", "Total", "Moneda", "Solicitado por", "Autorizado por",
                     "Código IFE", "Aval UTE", "Retención 2%", "Extranjero"]
ANCHOS_FACTURAS = [13, 11, 56, 24, 30, 15, 32, 15, 40, 22, 12, 11, 12, 8, 22, 22, 16, 18, 12, 10]
CAMPOS_LIQUIDACION = ["FUC", "Tipo de trámite", "Persona encargada", "Cédula persona encargada", "Persona responsable",
                      "Número de liquidación", "Fecha de liquidación", "Periodo desde", "Periodo hasta",
                      "Monto solicitado", "Decisión inicial", "Decisión inicial firmada", "Estado de cuenta adjunto",
                      "Devolución de efectivo"]
TRAMITES = '"Reintegro mensual,Liquidación final,Liquidación de vales"'


def _encabezado(ws, fila, columnas, anchos):
    for c, (h, w) in enumerate(zip(columnas, anchos), 1):
        celda = ws.cell(row=fila, column=c, value=h)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor=AZUL)
        celda.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[celda.column_letter].width = w


def _hoja_encabezado(wb, campos):
    ws = wb.active
    ws.title = "Encabezado"
    _encabezado(ws, 1, ["Campo", "Valor"], [34, 40])
    for i, (campo, valor) in enumerate(campos, 2):
        ws.cell(row=i, column=1, value=campo).font = Font(bold=True)
        ws.cell(row=i, column=2, value=valor)
    return ws


def _lista(ws, formula, rango):
    dv = DataValidation(type="list", formula1=formula, allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(rango)


def libro_liquidacion(encabezado: list[tuple], facturas: list[list], politica: dict,
                      movimientos: list[list] | None = None) -> Workbook:
    wb = Workbook()
    enc = _hoja_encabezado(wb, encabezado)
    filas = {campo: i for i, (campo, _) in enumerate(encabezado, 2)}
    if "Tipo de trámite" in filas:
        _lista(enc, TRAMITES, f"B{filas['Tipo de trámite']}")
    for campo in ("Decisión inicial firmada", "Estado de cuenta adjunto"):
        if campo in filas:
            _lista(enc, '"Sí,No"', f"B{filas[campo]}")

    ws = wb.create_sheet("Facturas")
    _encabezado(ws, 1, COLUMNAS_FACTURAS, ANCHOS_FACTURAS)
    ws.freeze_panes = "A2"
    for r in range(2, 202):  # formato texto: evita que Excel dañe la clave de 50 dígitos
        for c in (3, 4, 6, 8, 17):
            ws.cell(row=r, column=c).number_format = "@"
        ws.cell(row=r, column=1).number_format = "DD/MM/YYYY"
        for c in (11, 12, 13, 19):
            ws.cell(row=r, column=c).number_format = "#,##0.00"
    for r, fila in enumerate(facturas, 2):
        for c, v in enumerate(fila, 1):
            ws.cell(row=r, column=c, value=v)
    listas = wb.create_sheet("Listas")
    for i, cat in enumerate(politica.get("categorias_permitidas", []), 1):
        listas.cell(row=i, column=1, value=cat)
    for i, codigo in enumerate(sorted(politica.get("_catalogo") or {}), 1):
        listas.cell(row=i, column=4, value=codigo)
    listas.sheet_state = "hidden"
    n = max(1, len(politica.get("categorias_permitidas", [])))
    _lista(ws, f"=Listas!$A$1:$A${n}", "J2:J201")
    _lista(ws, '"01,04"', "B2:B201")
    _lista(ws, '"CRC,USD"', "N2:N201")
    _lista(ws, '"Sí,No"', "T2:T201")

    mov = wb.create_sheet("Movimientos bancarios")
    _encabezado(mov, 1, ["Fecha", "Descripción", "Monto"], [13, 50, 14])
    for r, fila in enumerate(movimientos or [], 2):
        for c, v in enumerate(fila, 1):
            mov.cell(row=r, column=c, value=v)
    return wb


def libro_arqueo(encabezado: list[tuple], efectivo: list[tuple], pendientes: list[list]) -> Workbook:
    wb = Workbook()
    enc = _hoja_encabezado(wb, encabezado)
    for i, (campo, _) in enumerate(encabezado, 2):
        if campo == "Tipo de arqueo":
            _lista(enc, '"Sin previo aviso,Programado"', f"B{i}")
    ws = wb.create_sheet("Efectivo")
    _encabezado(ws, 1, ["Denominación", "Cantidad", "Subtotal"], [16, 12, 16])
    for r, (d, c) in enumerate(efectivo, 2):
        ws.cell(row=r, column=1, value=d).number_format = "#,##0"
        ws.cell(row=r, column=2, value=c)
        ws.cell(row=r, column=3, value=f"=A{r}*B{r}").number_format = "#,##0.00"
    total = len(efectivo) + 2
    ws.cell(row=total, column=1, value="TOTAL EFECTIVO").font = Font(bold=True)
    ws.cell(row=total, column=3, value=f"=SUM(C2:C{total - 1})").number_format = "#,##0.00"
    ws = wb.create_sheet("Pendientes")
    _encabezado(ws, 1, ["Tipo", "Fecha", "Clave numérica", "Número", "Beneficiario / proveedor", "Descripción", "Monto"],
                [18, 12, 56, 24, 30, 40, 14])
    _lista(ws, '"Factura por liquidar,Vale,Adelanto"', "A2:A100")
    for r in range(2, 101):
        ws.cell(row=r, column=3).number_format = "@"
        ws.cell(row=r, column=4).number_format = "@"
    for r, fila in enumerate(pendientes, 2):
        for c, v in enumerate(fila, 1):
            ws.cell(row=r, column=c, value=v)
    return wb


DENOMINACIONES = [20000, 10000, 5000, 2000, 1000, 500, 100, 50, 25, 10, 5]


def crear_catalogo(ruta: Path, filas: list[list] | None = None) -> Path:
    """Plantilla del catálogo de cajas chicas (una fila por FUC)."""
    from .config import COLUMNAS_CATALOGO

    wb = Workbook()
    ws = wb.active
    ws.title = "Cajas"
    _encabezado(ws, 1, COLUMNAS_CATALOGO, [14, 34, 26, 16, 28, 15, 30, 30, 8])
    ws.freeze_panes = "A2"
    for r in range(2, 302):
        ws.cell(row=r, column=4).number_format = "@"
        ws.cell(row=r, column=6).number_format = "#,##0"
    for r, fila in enumerate(filas or [], 2):
        for c, v in enumerate(fila, 1):
            ws.cell(row=r, column=c, value=v)
    _lista(ws, '"Sí,No"', "I2:I301")
    nota = wb.create_sheet("Instrucciones")
    for i, t in enumerate([
        "Una fila por caja chica. Solo una caja por FUC (art. 4); excepciones en politica.yaml (apertura.excepciones_varias_cajas).",
        "Código caja (FUC): el mismo código que la persona encargada escribe en su liquidación y arqueo.",
        "Persona encargada: custodia el fondo. Solo puede tener una caja abierta a la vez (art. 5).",
        "Persona responsable (titular): firma la decisión inicial y puede hacer arqueos. Si no se indican aprobadores, es el aprobador.",
        "Monto del fondo: no puede superar el 10 % del monto de licitación reducida vigente (art. 13 b).",
        "Activa: 'No' para cajas cerradas; cualquier liquidación de una caja inactiva se marca como grave.",
    ], 1):
        nota.cell(row=i, column=1, value=t)
    nota.column_dimensions["A"].width = 120
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


def libro_registro_proveedor(datos: dict | None = None) -> Workbook:
    wb = Workbook()
    campos = [("Cédula", ""), ("Razón social", ""), ("Nombre comercial", ""), ("Correo", ""), ("Teléfono", "")]
    datos = datos or {}
    ws = _hoja_encabezado(wb, [(c, datos.get(c, v)) for c, v in campos])
    ws.title = "Registro"
    ws.cell(row=8, column=1, value="Complete y guarde este archivo en la carpeta 00_Registro. "
                                   "Su registro queda pendiente hasta que la Universidad lo apruebe.").font = Font(italic=True)
    return wb


def crear_plantillas(carpeta: Path, politica: dict) -> list[Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    liq = libro_liquidacion([(c, "Reintegro mensual" if c == "Tipo de trámite" else "") for c in CAMPOS_LIQUIDACION],
                            [], politica)
    p1 = carpeta / "Plantilla_Liquidacion_CajaChica.xlsx"
    liq.save(p1)
    arq = libro_arqueo([("FUC", ""), ("Persona encargada", ""), ("Fecha del arqueo", ""), ("Realizado por", ""),
                        ("Tipo de arqueo", "Sin previo aviso"), ("Fondo asignado", ""), ("Fecha de reposición", "")],
                       [(d, 0) for d in DENOMINACIONES], [])
    p2 = carpeta / "Plantilla_Arqueo_CajaChica.xlsx"
    arq.save(p2)
    p3 = carpeta / "Plantilla_Liquidacion_CajaChica.csv"
    with open(p3, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(["FUC", "Persona encargada", "Número de liquidación", "Fecha de liquidación",
                                "Monto solicitado", "Tipo de trámite", "Decisión inicial", "Decisión inicial firmada",
                                "Estado de cuenta adjunto", "Devolución de efectivo"] + COLUMNAS_FACTURAS)
    p4 = carpeta / "Plantilla_Registro_Proveedor.xlsx"
    libro_registro_proveedor().save(p4)
    p5 = carpeta / "INSTRUCCIONES.txt"
    inst = politica["institucion"]
    p5.write_text(f"""CÓMO ENTREGAR LA LIQUIDACIÓN Y EL ARQUEO DE CAJA CHICA
=====================================================

PERSONAS ENCARGADAS DE CAJA CHICA
1. Use la plantilla de liquidación o de arqueo de esta carpeta. No cambie los nombres de las columnas.
2. En el Encabezado indique el FUC, el tipo de trámite (reintegro mensual, liquidación final o de vales) y el número
   de la decisión inicial firmada por la persona responsable.
3. Una fila por factura. La clave numérica tiene 50 dígitos: péguela tal cual (la columna ya está en formato Texto).
   Indique el código IFE de Sigesa y, si la compra lo requiere, el oficio de aval de la UTE.
4. TODA factura debe venir a nombre de:
      {inst.get('nombre')}
      Cédula jurídica {inst.get('cedula_juridica')}
   No se aceptan tiquetes electrónicos (no traen los datos de la Universidad).
5. Copie los movimientos de la cuenta bancaria del período en la hoja "Movimientos bancarios".
6. El reintegro mensual se entrega a más tardar el 5.º día hábil del mes siguiente.
7. Guarde el archivo como  Liquidacion_FUC-1201_2026-09.xlsx  o  Arqueo_FUC-1201_2026-09-30.xlsx  y súbalo a 01_Entrada.
8. El resultado aparece en 03_Revisiones. Si hay que corregir, corrija el mismo archivo (mismo número) y vuelva a subirlo.

PROVEEDORES (carpeta 07_Proveedores)
1. Regístrese una sola vez: complete Plantilla_Registro_Proveedor.xlsx y súbala a 00_Registro.
2. Por cada factura suba tres archivos, cada uno en su carpeta:
      01_PDF                   el PDF de la factura
      02_XML                   el XML de la factura electrónica
      03_Respuesta_Hacienda    el XML de respuesta (aceptación) de Hacienda
   No hace falta renombrarlos: se unen por la clave de 50 dígitos.
""", encoding="utf-8")
    return [p1, p2, p3, p4, p5]


# ------------------------------------------------------------------ demostración

def _clave(fecha_: date, cedula: str, numero: int, tipo="01") -> str:
    consecutivo = f"00100001{tipo}{numero:010d}"  # sucursal 001 + terminal 00001 + tipo + número
    return f"506{fecha_:%d%m%y}{solo_digitos(cedula).zfill(12)}{consecutivo}1{random.randint(10**7, 10**8 - 1)}"


CATALOGO_DEMO = [
    ["FUC-1201", "Escuela de Administración", "María Fernández", "1-1111-1111", "Carlos Rojas", 500000, "", "", "Sí"],
    ["FUC-2305", "Sede Regional Chorotega", "Laura Vega", "1-2222-2222", "Roberto Méndez", 300000, "", "", "Sí"],
    ["FUC-3110", "Escuela de Química", "Andrés Quesada", "1-3333-3333", "Sofía Arias", 250000, "", "", "Sí"],
    ["FUC-4020", "Biblioteca Joaquín García Monge", "Diana Brenes", "1-4444-4444", "Esteban Mora", 400000, "", "", "Sí"],
    ["FUC-5501", "Vicerrectoría de Docencia", "Karla Salas", "1-5555-5555", "Marco Vargas", 150000, "", "", "Sí"],
    ["FUC-6203", "Escuela de Informática", "Óscar Rojas", "1-6666-6666", "Marco Vargas", 200000, "", "", "Sí"],
    ["FUC-7004", "Facultad de Ciencias Sociales", "Diana Brenes", "1-4444-4444", "Ana Solano", 200000, "", "", "Sí"],
]

PROVEEDORES_DEMO = {
    "3101456789": ("Librería El Estudiante S.A.", "Aprobado"),
    "3101222333": ("Super Central S.A.", "Aprobado"),
    "3101777888": ("Ferretería Industrial S.A.", "Aprobado"),
    "4000042151": ("Correos de Costa Rica S.A.", "Aprobado"),
}


def crear_demo(carpeta: Path, politica: dict) -> list[Path]:
    random.seed(7)
    inst = politica["institucion"]
    NOM, CED = inst["nombre"], inst["cedula_juridica"]
    d = date.fromisoformat

    def fac(fecha_, prov, ced_prov, num, desc, cat, total, sol, aut, receptor=NOM, ced_rec=CED, tipo="01",
            ife="IFE-", aval="", retencion=None, extranjero="No", moneda="CRC", clave=None):
        sub = round(total / 1.13, 2)
        iva = round(total - sub, 2)
        clave = clave if clave is not None else _clave(fecha_, ced_prov, num, tipo)
        ife = f"IFE-{num:06d}" if ife == "IFE-" else ife
        return [fecha_, tipo, clave, clave[21:41] if clave else f"EXT-{num}", prov, ced_prov, receptor, ced_rec, desc,
                cat, sub, iva, total, moneda, sol, aut, ife, aval, retencion, extranjero]

    rutas = []
    carpeta.mkdir(parents=True, exist_ok=True)

    # ---- Liquidación de agosto (FUC-1201): fuera de plazo, sin decisión inicial, fragmentación, banco sin conciliar
    ago = [
        fac(d("2026-08-13"), "Ferretería Industrial S.A.", "3-101-777888", 4380, "Pintura para pasillo", "Mantenimiento menor", 4800, "Luis Solís", "Carlos Rojas"),
        fac(d("2026-08-13"), "Ferretería Industrial S.A.", "3-101-777888", 4381, "Brochas y rodillos", "Mantenimiento menor", 3100, "Luis Solís", "Carlos Rojas"),
        fac(d("2026-08-14"), "Ferretería Industrial S.A.", "3-101-777888", 4392, "Pintura segunda mano", "Mantenimiento menor", 4650, "Luis Solís", "Carlos Rojas"),
        fac(d("2026-08-18"), "Soda El Buen Sabor", "1-0555-0444", 1203, "Almuerzo de trabajo en restaurante", "Alimentación", 6900, "Ana Mora", "Carlos Rojas"),
        fac(d("2026-08-19"), "Super Central S.A.", "3-101-222333", 87990, "Productos de limpieza", "Limpieza", 7180, "Ana Mora", ""),
        fac(d("2026-08-20"), "Parqueo Central", "3-101-121212", 802, "Parqueo gestión en Hacienda", "Parqueos y peajes", 1500, "Carlos Rojas", "Carlos Rojas"),
    ]
    soda = ago[3]
    movimientos_ago = [[f[0], f"Compra {f[4]}", f[12]] for f in ago if f[4] != "Super Central S.A."]
    movimientos_ago.append([d("2026-08-21"), "Retiro en cajero automático", 20000])
    enc_ago = [("FUC", "FUC-1201"), ("Tipo de trámite", "Reintegro mensual"), ("Persona encargada", "María Fernández"),
               ("Cédula persona encargada", "1-1111-1111"), ("Persona responsable", "Carlos Rojas"),
               ("Número de liquidación", "LQ-1201-2026-08"), ("Fecha de liquidación", d("2026-09-10")),
               ("Periodo desde", d("2026-08-01")), ("Periodo hasta", d("2026-08-31")),
               ("Monto solicitado", sum(f[12] for f in ago)), ("Decisión inicial", ""), ("Decisión inicial firmada", ""),
               ("Estado de cuenta adjunto", ""), ("Devolución de efectivo", "")]
    p = carpeta / "Liquidacion_FUC-1201_2026-08.xlsx"
    libro_liquidacion(enc_ago, ago, politica, movimientos_ago).save(p)
    rutas.append(p)

    # ---- Liquidación de setiembre (FUC-1201): reincide en faltas leves
    libreria = fac(d("2026-09-03"), "Librería El Estudiante S.A.", "3-101-456789", 1520, "Resmas de papel", "Materiales de oficina", 8500, "Ana Mora", "Carlos Rojas")
    super_c = fac(d("2026-09-04"), "Super Central S.A.", "3-101-222333", 88121, "Café y galletas para reunión con visitantes externos", "Atención a visitantes", 6450, "Ana Mora", "Carlos Rojas", retencion=50)
    correos = fac(d("2026-09-07"), "Correos de Costa Rica S.A.", "4-000-042151", 3310, "Envío de documentos a la Sede Regional", "Correos y envíos", 4200, "Luis Solís", "Carlos Rojas")
    brochas = fac(d("2026-09-09"), "Ferretería Industrial S.A.", "3-101-777888", 4415, "Brochas para mantenimiento", "Mantenimiento menor", 2950, "Luis Solís", "Carlos Rojas")
    sep = [
        libreria, super_c, correos, list(libreria),
        fac(d("2026-09-08"), "Minisúper La Esquina", "1-0987-0654", 776, "Refrescos varios", "Alimentación", 3800, "Luis Solís", "Carlos Rojas", tipo="04", receptor="", ced_rec=""),
        fac(d("2026-09-08"), "Ferretería Industrial S.A.", "3-101-777888", 4410, "Candado para bodega", "Mantenimiento menor", 5300, "Luis Solís", "Carlos Rojas", receptor="Luis Solís Vargas", ced_rec="1-1234-0567"),
        brochas,
        fac(d("2026-09-10"), "Licorera Nacional", "3-101-999000", 5521, "Vino y cerveza para despedida", "Atención a visitantes", 9000, "Ana Mora", "Carlos Rojas"),
        fac(d("2026-09-14"), "Tecno Store S.A.", "3-101-555111", 9912, "Licencia de software de diseño", "Materiales de oficina", 8900, "Ana Mora", "Carlos Rojas"),
        fac(d("2026-09-15"), "Tecno Store S.A.", "3-101-555111", 9940, "Monitor de 24 pulgadas", "Materiales de oficina", 135000, "Ana Mora", "Carlos Rojas"),
        fac(d("2026-09-16"), "Parqueo Central", "3-101-121212", 845, "Parqueo gestión en Tributación", "Parqueos y peajes", 1500, "Carlos Rojas", "Roberto Méndez", ife=""),
    ]
    enc_sep = [("FUC", "FUC-1201"), ("Tipo de trámite", "Reintegro mensual"), ("Persona encargada", "María Fernández"),
               ("Cédula persona encargada", "1-1111-1111"), ("Persona responsable", "Carlos Rojas"),
               ("Número de liquidación", "LQ-1201-2026-09"), ("Fecha de liquidación", d("2026-10-01")),
               ("Periodo desde", d("2026-09-01")), ("Periodo hasta", d("2026-09-30")),
               ("Monto solicitado", sum(f[12] for f in sep)), ("Decisión inicial", "DI-1201-2026-014"),
               ("Decisión inicial firmada", "Sí"), ("Estado de cuenta adjunto", ""), ("Devolución de efectivo", "")]
    p = carpeta / "Liquidacion_FUC-1201_2026-09.xlsx"
    libro_liquidacion(enc_sep, sep, politica).save(p)
    rutas.append(p)

    # ---- Liquidación final en CSV (FUC-2305): sin estado de cuenta, gastos en el extranjero, monto no cuadra
    ops = [
        fac(d("2026-09-15"), "Estación de Servicio La Uruca", "3-101-343434", 70011, "Combustible vehículo institucional", "Combustible", 9800, "Pedro Jiménez", "Roberto Méndez"),
        fac(d("2026-09-19"), "Taxi Unidos", "3-101-656565", 3321, "Taxi traslado de equipo", "Transporte", 7800, "Pedro Jiménez", "Roberto Méndez"),
        fac(d("2026-08-10"), "Fotocopiadora Rápida", "1-0777-0888", 2210, "Copias de expedientes", "Fotocopias e impresión", 5650, "Pedro Jiménez", "Roberto Méndez"),
        fac(d("2026-09-20"), "Pedro Jiménez Arias", "1-0999-0111", 15, "Reparación menor de silla", "Mantenimiento menor", 6000, "Pedro Jiménez", "Roberto Méndez"),
        fac(d("2026-09-21"), "Imprenta Gráfica S.A.", "3-101-898989", 6610, "Impresión de afiches del congreso", "Fotocopias e impresión", 8400, "Pedro Jiménez", "Roberto Méndez"),
        fac(d("2026-09-22"), "Amazon.com", "", 1, "Cable adaptador para proyector", "Materiales de oficina", 15, "Pedro Jiménez", "Roberto Méndez",
            ced_rec="", ife="", extranjero="Sí", moneda="USD", clave=""),
        fac(d("2026-09-23"), "Hotel Plaza Panamá", "", 2, "Hospedaje en gira académica", "Otros gastos menores", 18, "Pedro Jiménez", "Roberto Méndez",
            receptor="Pedro Jiménez", ced_rec="", ife="", extranjero="Sí", moneda="USD", clave=""),
    ]
    ops[1][11] = 1900  # IVA mal digitado
    p = carpeta / "Liquidacion_FUC-2305_final.csv"
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["FUC", "Persona encargada", "Número de liquidación", "Fecha de liquidación", "Monto solicitado",
                    "Tipo de trámite", "Decisión inicial", "Decisión inicial firmada", "Estado de cuenta adjunto",
                    "Devolución de efectivo"] + COLUMNAS_FACTURAS)
        for fila in ops:
            w.writerow(["FUC-2305", "Laura Vega", "LF-2305-2026", "29/09/2026", "60000", "Liquidación final",
                        "DI-2305-2026-003", "Sí", "No", ""] +
                       [x.strftime("%d/%m/%Y") if isinstance(x, date) else ("" if x is None else x) for x in fila])
    rutas.append(p)

    # ---- Arqueo (FUC-1201): programado, faltante repuesto tarde, vale vencido, pendiente ya reintegrado
    efectivo = [(20000, 23), (5000, 1), (500, 1), (100, 2)]
    pendientes = [
        ["Factura por liquidar", d("2026-09-03"), libreria[2], libreria[3], "Librería El Estudiante S.A.", "Resmas de papel", 8500],
        ["Factura por liquidar", d("2026-09-29"), "", "771", "Super Central S.A.", "Agua embotellada", 4800],
        ["Vale", d("2026-09-21"), "", "V-118", "Luis Solís", "Compra de repuestos (pendiente factura)", 9000],
    ]
    p = carpeta / "Arqueo_FUC-1201_2026-09-30.xlsx"
    libro_arqueo([("FUC", "FUC-1201"), ("Persona encargada", "María Fernández"), ("Fecha del arqueo", d("2026-09-30")),
                  ("Realizado por", "Carlos Rojas"), ("Tipo de arqueo", "Programado"), ("Fondo asignado", 500000),
                  ("Fecha de reposición", d("2026-10-01"))], efectivo, pendientes).save(p)
    rutas.append(p)

    rutas += crear_demo_proveedores(carpeta.parent / "07_Proveedores", politica,
                                    {"libreria": libreria, "super": super_c, "brochas": brochas, "correos": correos,
                                     "soda": soda})
    return rutas


# ------------------------------------------------------------------ demostración: comprobantes de proveedores

NS_FE = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica"
NS_MH = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/mensajeHacienda"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"


def _xml_factura(ruta, clave, fecha_, emisor, ced_emisor, receptor, ced_receptor, detalle, total):
    ET.register_namespace("", NS_FE)
    ET.register_namespace("ds", NS_DS)
    q = lambda t: f"{{{NS_FE}}}{t}"
    raiz = ET.Element(q("FacturaElectronica"))

    def hijo(padre, tag, texto=None):
        e = ET.SubElement(padre, q(tag))
        if texto is not None:
            e.text = str(texto)
        return e
    hijo(raiz, "Clave", clave)
    hijo(raiz, "NumeroConsecutivo", clave[21:41])
    hijo(raiz, "FechaEmision", f"{fecha_.isoformat()}T10:15:00-06:00")
    em = hijo(raiz, "Emisor")
    hijo(em, "Nombre", emisor)
    i = hijo(em, "Identificacion")
    hijo(i, "Tipo", "02" if solo_digitos(ced_emisor).startswith("3") else "01")
    hijo(i, "Numero", solo_digitos(ced_emisor))
    hijo(em, "CorreoElectronico", "facturacion@ejemplo.cr")
    re_ = hijo(raiz, "Receptor")
    hijo(re_, "Nombre", receptor)
    i = hijo(re_, "Identificacion")
    hijo(i, "Tipo", "02")
    hijo(i, "Numero", solo_digitos(ced_receptor))
    det = hijo(raiz, "DetalleServicio")
    linea = hijo(det, "LineaDetalle")
    hijo(linea, "NumeroLinea", 1)
    hijo(linea, "Detalle", detalle)
    sub = round(total / 1.13, 2)
    res = hijo(raiz, "ResumenFactura")
    mon = hijo(res, "CodigoTipoMoneda")
    hijo(mon, "CodigoMoneda", "CRC")
    hijo(mon, "TipoCambio", 1)
    hijo(res, "TotalVenta", f"{sub:.2f}")
    hijo(res, "TotalImpuesto", f"{total - sub:.2f}")
    hijo(res, "TotalComprobante", f"{total:.2f}")
    firma = ET.SubElement(raiz, f"{{{NS_DS}}}Signature")
    ET.SubElement(firma, f"{{{NS_DS}}}SignatureValue").text = "FIRMA-DE-DEMOSTRACION"
    ET.ElementTree(raiz).write(ruta, encoding="utf-8", xml_declaration=True)


def _xml_respuesta(ruta, clave, emisor, ced_emisor, receptor, ced_receptor, total, mensaje="1", detalle=""):
    ET.register_namespace("", NS_MH)
    q = lambda t: f"{{{NS_MH}}}{t}"
    raiz = ET.Element(q("MensajeHacienda"))
    for tag, val in [("Clave", clave), ("NombreEmisor", emisor), ("TipoIdentificacionEmisor", "02"),
                     ("NumeroCedulaEmisor", solo_digitos(ced_emisor)), ("NombreReceptor", receptor),
                     ("TipoIdentificacionReceptor", "02"), ("NumeroCedulaReceptor", solo_digitos(ced_receptor)),
                     ("Mensaje", mensaje), ("DetalleMensaje", detalle or "Este comprobante fue aceptado."),
                     ("MontoTotalImpuesto", f"{total - round(total / 1.13, 2):.2f}"), ("TotalFactura", f"{total:.2f}")]:
        ET.SubElement(raiz, q(tag)).text = str(val)
    ET.ElementTree(raiz).write(ruta, encoding="utf-8", xml_declaration=True)


def _pdf_factura(ruta, clave, fecha_, emisor, ced_emisor, receptor, ced_receptor, detalle, total, escaneado=False):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    if escaneado:  # imita una factura fotografiada: solo trazos, sin texto extraíble
        pdf.set_draw_color(120, 120, 120)
        for y in range(20, 200, 12):
            pdf.line(20, y, 190, y)
        pdf.rect(15, 15, 180, 190)
        pdf.output(str(ruta))
        return
    sub = round(total / 1.13, 2)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, "FACTURA ELECTRONICA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for linea in [f"Emisor: {emisor}", f"Cedula: {ced_emisor}", f"Consecutivo: {clave[21:41]}",
                  f"Clave: {' '.join(clave[i:i + 10] for i in range(0, 50, 10))}",
                  f"Fecha: {fecha_:%d/%m/%Y}", f"Receptor: {receptor}", f"Cedula receptor: {ced_receptor}", "",
                  f"Detalle: {detalle}", f"Subtotal: CRC {sub:,.2f}", f"IVA 13%: CRC {total - sub:,.2f}",
                  f"TOTAL: CRC {total:,.2f}", "", "Documento de demostracion"]:
        pdf.cell(0, 7, linea, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(ruta))


def crear_demo_proveedores(base: Path, politica: dict, facturas: dict) -> list[Path]:
    from .comprobantes import CARPETAS, RUTA_PROVEEDORES, guardar_proveedores
    rutas = {k: base / v for k, v in CARPETAS.items()}
    for r in rutas.values():
        r.mkdir(parents=True, exist_ok=True)
    inst = politica["institucion"]
    NOM, CED = inst["nombre"], inst["cedula_juridica"]
    if not RUTA_PROVEEDORES.exists():
        guardar_proveedores({ced: {"cedula": ced, "razon_social": n, "nombre_comercial": "", "correo": "", "telefono": "",
                                   "estado": e, "fecha_registro": "2026-01-15", "observaciones": "Demostración"}
                             for ced, (n, e) in PROVEEDORES_DEMO.items()})
    creados = []

    def juego(nombre, f, pdf=True, xml=True, resp=True, total_pdf=None, mensaje="1", detalle_msj="",
              receptor=NOM, ced_receptor=CED, escaneado=False):
        fecha_, clave, emisor, ced = f[0], f[2], f[4], f[5]
        total = f[12]
        if pdf:
            p = rutas["pdf"] / (f"Factura_{clave[21:41]}.pdf" if escaneado else f"{nombre}.pdf")
            _pdf_factura(p, clave, fecha_, emisor, ced, receptor, ced_receptor, f[8], total_pdf or total, escaneado)
            creados.append(p)
        if xml:
            p = rutas["xml"] / f"{nombre}.xml"
            _xml_factura(p, clave, fecha_, emisor, ced, receptor, ced_receptor, f[8], total)
            creados.append(p)
        if resp:
            p = rutas["respuesta"] / f"Respuesta_{nombre}.xml"
            _xml_respuesta(p, clave, emisor, ced, receptor, ced_receptor, total, mensaje, detalle_msj)
            creados.append(p)

    juego("Libreria_1520", facturas["libreria"])                              # todo cuadra
    juego("SuperCentral_88121", facturas["super"], total_pdf=9450)            # PDF con otro total
    juego("Ferreteria_4415", facturas["brochas"], mensaje="3",                # rechazada por Hacienda
          detalle_msj="Rechazado: el receptor indicado no coincide con el registro.")
    juego("Correos_3310", facturas["correos"], pdf=False, resp=False)         # incompleto: solo XML
    juego("Soda_1203", facturas["soda"])                                      # proveedor no registrado
    oficentro = [date(2026, 9, 24), "01", _clave(date(2026, 9, 24), "3-101-343434", 5550), "", "Distribuidora Oficentro S.A.",
                 "3-101-343434", "", "", "Lapiceros y folders", "", 0, 0, 7350]
    juego("Oficentro_5550", oficentro, receptor="Pedro Jiménez Arias", ced_receptor="1-0999-0111")  # no es la UNA
    imprenta = [date(2026, 9, 21), "01", _clave(date(2026, 9, 21), "3-101-898989", 6610), "", "Imprenta Gráfica S.A.",
                "3-101-898989", "", "", "Impresión de afiches del congreso", "", 0, 0, 8400]
    juego("Imprenta_6610", imprenta, escaneado=True)                          # PDF escaneado: revisión visual

    registro = rutas["registro"] / "Registro_Imprenta_Grafica.xlsx"
    libro_registro_proveedor({"Cédula": "3-101-898989", "Razón social": "Imprenta Gráfica S.A.",
                              "Nombre comercial": "Imprenta Gráfica", "Correo": "ventas@imprentagrafica.cr",
                              "Teléfono": "2222-3333"}).save(registro)
    creados.append(registro)
    return creados
