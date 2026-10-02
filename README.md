# Agente de Control de Caja Chica — Universidad Nacional

Revisa automáticamente las liquidaciones y los arqueos de caja chica, factura por factura, contra la
política de la institución, y lleva un dashboard histórico del gasto.

## Cómo funciona

```
Custodios ──► OneDrive / Google Drive ──► 01_Entrada ──► run.py procesar ──► 03_Revisiones (Excel por archivo)
                                                              │                 05_Dashboard (HTML)
                                                              └──► data/cajachica.db (histórico)
```

Carpetas del repositorio compartido:

| Carpeta | Quién la usa | Qué contiene |
|---|---|---|
| `00_Plantillas` | Custodios | Plantillas de liquidación (Excel/CSV) y arqueo, e instrucciones |
| `01_Entrada` | Custodios | Aquí dejan sus archivos |
| `02_Procesados` | Agente | Originales ya revisados, por mes |
| `03_Revisiones` | Custodios y usted | Informe Excel: resumen, factura por factura, hallazgos |
| `04_Rechazados` | Custodios | Archivos ilegibles, con una nota de por qué |
| `05_Dashboard` | Revisores | Acceso directo al dashboard publicado (con registro obligatorio) |
| `06_Informes` | Usted | Informe consolidado de incumplimientos de todas las unidades |
| `07_Proveedores` | Proveedores | `00_Registro`, `01_PDF`, `02_XML`, `03_Respuesta_Hacienda`; el agente archiva en `04_Conciliados` |

## Comprobantes de proveedores

Los proveedores se registran con `Plantilla_Registro_Proveedor.xlsx` (en `07_Proveedores/00_Registro`) y por
cada factura suben tres archivos a carpetas separadas: el PDF, el XML de la factura y el XML de respuesta de
Hacienda. El agente los une por la clave de 50 dígitos, cruza que los tres coincidan y deja cada comprobante
en la sección **Aprobación de comprobantes** del dashboard, donde la jefatura aprueba, devuelve o rechaza.

## Qué revisa (Reglamento de Cajas Chicas de la UNA)

Cada liquidación y cada arqueo recibe una **lista de verificación** con estado CUMPLE / NO CUMPLE / NO SE
PUEDE VERIFICAR / NO APLICA por artículo, y cada hallazgo una **gravedad sugerida** (arts. 20–22, con
reincidencia en 3 meses). Además de lo de abajo: decisión inicial firmada, código IFE, retención del 2 %,
avales de UTE (arts. 7, 7 bis, 7 ter), estado de cuenta y devolución en liquidaciones finales, plazos en días
hábiles (reintegro al 5.º día hábil, vales en 5 días hábiles, faltantes el mismo día, sobrantes al día
siguiente), conciliación contra movimientos bancarios (art. 11 h), gastos en el extranjero (art. 10) y reglas
de apertura del catálogo (una caja por FUC y por persona encargada, fondo ≤ 10 % de licitación reducida).

### Controles base

**Cada factura**: datos de la institución (nombre y cédula jurídica del receptor), clave de 50 dígitos
de Hacienda (y que su fecha, emisor y consecutivo coincidan con lo digitado), tipo de comprobante
(rechaza tiquetes), límite por gasto, cálculo de IVA, antigüedad, período, categoría autorizada,
conceptos prohibidos o sensibles, aprobación y conflicto de interés (proveedor = custodio/solicitante).

**Duplicados**: misma clave o mismo proveedor + número (dentro del archivo y contra todo el histórico),
posibles duplicados (mismo proveedor, fecha y monto con otro número; mismo número con otro proveedor) y
compras repetidas.

**Por liquidación**: fraccionamiento de compras, monto solicitado vs. facturas, total vs. fondo.

**Arqueos**: faltantes y sobrantes, fondo declarado vs. asignado, independencia de quien arquea, vales y
facturas pendientes vencidos, y facturas del arqueo que ya fueron reintegradas en una liquidación.

## Prueba rápida con datos de demostración

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py demo        # catálogo de 6 cajas y 4 archivos con irregularidades sembradas
.venv/bin/python run.py procesar    # revisa todo y genera los informes y el dashboard
.venv/bin/python run.py informe 30  # informe consolidado de incumplimientos
```

Los resultados quedan en `repositorio/03_Revisiones`, `repositorio/06_Informes` y `reportes/`.
El dashboard (`reportes/dashboard.html`) exige registro del revisor, por lo que solo se consulta
publicado como artifact de claude.ai; abierto como archivo local muestra el aviso de acceso.

## Puesta en marcha

0. Copie `config/politica.ejemplo.yaml` a `config/politica.yaml`. La copia real queda fuera de git
   (`.gitignore`), igual que el catálogo, la base de datos y las liquidaciones: así ningún dato de la
   institución llega al repositorio.
1. Edite `config/politica.yaml`: nombre y cédula jurídica de la institución, fondos por caja, límites,
   categorías y la ruta `repositorio` (su carpeta de OneDrive o Google Drive).
2. `.venv/bin/python run.py iniciar` crea las carpetas y plantillas en el repositorio.
3. Comparta la carpeta con los custodios (permiso de edición en `01_Entrada`).
4. Cada semana: `.venv/bin/python run.py procesar`, o pídale a Claude en este proyecto
   "procesa la semana" para obtener además el análisis ejecutivo.

Para borrar los datos de demostración: elimine `data/`, `reportes/`, el contenido de `repositorio/` y
`config/Catalogo_Cajas.xlsx`.
