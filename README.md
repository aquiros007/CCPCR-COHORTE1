# Agente de Control de Caja Chica — Universidad Nacional

Revisa las liquidaciones, reintegros, vales y arqueos de las cajas chicas de la Universidad Nacional (Costa
Rica) contra el Reglamento de Cajas Chicas, factura por factura. Cruza los comprobantes electrónicos que
entregan los proveedores, lleva un dashboard histórico con registro de quién revisa, y respalda todo en
Google Drive.

## Dónde corre

Todo el flujo funciona en **Railway** (`portal_web/`), sin depender de ninguna computadora:

- **Personas encargadas**: la administración las invita por FUC; entregan su liquidación o arqueo en el
  portal, el motor (`cajachica/`) lo revisa al instante y ven su lista de verificación, hallazgos y Excel.
- **Proveedores**: se registran y envían PDF + XML + respuesta de Hacienda; el cruce entra al motor.
- **Administración**: dashboard de caja chica, entregas, decisiones sobre facturas, catálogo, política,
  informe consolidado y bitácora.
- **Datos**: Postgres (cuentas, envíos, validaciones, bitácora) y un volumen persistente en `/data`
  (base del motor, entregas, revisiones, informes); respaldo en Google Drive cuando hay credenciales.

Los comandos de `run.py` siguen sirviendo para trabajar en una computadora con carpetas locales.

## Cómo funciona

```
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │ 0. CONFIGURACIÓN (una vez, y cuando cambie la política)                          │
 │    config/politica.yaml ....... reglamento, límites, plazos, feriados, artículos │
 │    config/Catalogo_Cajas.xlsx . 120 cajas: FUC, persona encargada, titular,      │
 │                                 fondo, aprobadores                               │
 │    config/Proveedores.xlsx .... registro de proveedores (Pendiente / Aprobado)   │
 │    politicas/ ................. documento oficial del reglamento                 │
 └──────────────────────────────────────┬───────────────────────────────────────────┘
                                        │
                                        ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │ 1. ENTREGA DE DOCUMENTOS                                                         │
 │                                                                                  │
 │  Personas encargadas (por FUC)          Proveedores                              │
 │  ─────────────────────────────          ───────────                              │
 │  Plantilla de liquidación o arqueo      Portal web de proveedores (Railway)      │
 │  (Excel o CSV) con:                       · registro: cédula, razón social       │
 │   · encabezado: FUC, tipo de trámite,     · por factura: PDF + XML +             │
 │     decisión inicial, estado de cuenta      respuesta de Hacienda                │
 │   · una fila por factura (clave, IFE,     · verificación inmediata en el         │
 │     aval UTE, retención 2 %)                navegador antes de enviar            │
 │   · movimientos bancarios               o carpetas en 07_Proveedores/            │
 │                                           00_Registro · 01_PDF · 02_XML ·        │
 │                                           03_Respuesta_Hacienda                  │
 │                                                                                  │
 │            │                     portal ──► run.py importar-web                  │
 │            ▼                                         ▼                           │
 │   repositorio/01_Entrada                repositorio/07_Proveedores               │
 └────────────┬─────────────────────────────────────────┬───────────────────────────┘
              │                                         │
              ▼                                         ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │ 2. PROCESAMIENTO  ·  run.py procesar  (o "procesa la semana" con Claude)         │
 │                                                                                  │
 │  2a. Comprobantes de proveedores (cajachica/comprobantes.py)                     │
 │      une PDF + XML + respuesta por la clave de 50 dígitos y cruza 15 controles:  │
 │      Hacienda aceptó · emisor, total e IVA iguales · a nombre de la UNA ·        │
 │      firma presente · clave y total en el PDF · proveedor aprobado · no repetido │
 │      ──► LISTO PARA APROBACIÓN / CON DIFERENCIAS / REVISIÓN MANUAL / INCOMPLETO  │
 │      ──► juego completo archivado en 07_Proveedores/04_Conciliados               │
 │                                    │                                             │
 │                                    ▼                                             │
 │  2b. Lectura de liquidaciones y arqueos (cajachica/lectura.py)                   │
 │      reconoce columnas aunque cambien de nombre; ilegible ──► 04_Rechazados      │
 │                                    │                                             │
 │                                    ▼                                             │
 │  2c. Reglas (cajachica/reglas.py)                                                │
 │      · cada factura: a nombre de la UNA, clave de Hacienda, tiquete, IFE,        │
 │        límite ₡, IVA, fechas, categoría, compras prohibidas, aval de UTE,        │
 │        retención 2 %, extranjero, aprobador, conflicto de interés,               │
 │        cruce contra el XML del proveedor                                         │
 │      · duplicados dentro del archivo y contra todo el histórico                  │
 │      · liquidación: decisión inicial, fragmentación, monto vs. facturas y        │
 │        fondo, plazos en días hábiles, movimientos bancarios, liquidación final   │
 │      · arqueo: faltante/sobrante y su reposición, vales vencidos, pendientes     │
 │        ya reintegrados, arqueo sin previo aviso, quién lo hace                   │
 │      · catálogo: caja registrada, persona encargada, una caja por FUC            │
 │                                    │                                             │
 │                                    ▼                                             │
 │  2d. Lista de verificación y gravedad (cajachica/verificacion.py)                │
 │      CUMPLE / NO CUMPLE / NO SE PUEDE VERIFICAR / NO APLICA por artículo         │
 │      gravedad sugerida Leve / Grave / Muy grave (arts. 20–22),                   │
 │      escalada por reincidencia en 90 días · aviso del art. 23                    │
 │                                    │                                             │
 │                                    ▼                                             │
 │  2e. Registro histórico  ──►  data/cajachica.db (SQLite)                         │
 └──────────────┬─────────────────────┬──────────────────────┬──────────────────────┘
                │                     │                      │
                ▼                     ▼                      ▼
 ┌──────────────────────┐ ┌───────────────────────┐ ┌───────────────────────────────┐
 │ 3a. REVISIÓN POR     │ │ 3b. INFORME           │ │ 3c. DASHBOARD (claude.ai)     │
 │     ARCHIVO          │ │     CONSOLIDADO       │ │                               │
 │ 03_Revisiones/<mes>  │ │ run.py informe        │ │ registro obligatorio del      │
 │ · resumen            │ │ 06_Informes           │ │ revisor (rol, motivo)         │
 │ · lista de           │ │ · semáforo por FUC    │ │ · gasto, hallazgos, entregas  │
 │   verificación       │ │ · documentos          │ │   por unidad, arqueos         │
 │ · puntos que cumplen │ │   incumplidos con     │ │ · validar evidencia de cada   │
 │ · documentos         │ │   artículo, gravedad  │ │   hallazgo                    │
 │   pendientes         │ │   y acción            │ │ · aprobar / devolver /        │
 │ · factura por        │ │ · apertura y catálogo │ │   rechazar comprobantes       │
 │   factura            │ │ · sin entrega, sin    │ │ · confirmar vigencia          │
 │ · hallazgos          │ │   arqueo reciente     │ │ · bitácora (admin)            │
 │ (vuelve a la persona │ │ · comprobantes de     │ │                               │
 │  encargada)          │ │   proveedores         │ │ el portal recibe el estado    │
 └──────────┬───────────┘ └───────────┬───────────┘ └──────────────┬────────────────┘
            │                         │                            │
            └─────────────────────────┼────────────────────────────┘
                                      ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │ 4. ANÁLISIS DE AUDITOR (Claude)                                                  │
 │    · duplicados: ¿error, reintento de cobro o patrón?                            │
 │    · pertinencia del gasto (art. 3) y reglas cualitativas                        │
 │    · revisión visual de PDF escaneados y alteraciones (art. 6 d)                 │
 │    · veredicto por liquidación: reintegrar / parcial / devolver                  │
 │    · hechos separados de inferencias; nunca afirma fraude                        │
 └──────────────────────────────────────┬───────────────────────────────────────────┘
                                        │
                                        ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │ 5. RESPALDO EN GOOGLE DRIVE  ·  carpeta "Caja Chica U"                           │
 │    run.py respaldo-local (Drive para escritorio) o respaldo-pendiente (conector) │
 │                                                                                  │
 │    01_Facturas/<año>/<MM-Mes>/<cédula> <proveedor>/<n.º factura>/                │
 │      Factura_<n>.pdf · Factura_<n>.xml · Respuesta_Hacienda_<n>.xml              │
 │    02_Proveedores ............ registro de proveedores (versionado)              │
 │    03_Liquidaciones_y_Arqueos/<mes> ... originales entregados                    │
 │    04_Revisiones/<mes> ....... revisión de cada archivo                          │
 │    05_Informes_Consolidados .. informes de incumplimientos                       │
 │    06_Bitacora_de_Revision ... ingresos, validaciones y aprobaciones (CSV)       │
 │    07_Configuracion_y_Politicas ... política, catálogo, plantillas               │
 │    08_Base_de_Datos .......... copia consistente de la base SQLite               │
 └──────────────────────────────────────────────────────────────────────────────────┘
```

## Carpetas del repositorio de trabajo

| Carpeta | Quién la usa | Qué contiene |
|---|---|---|
| `00_Plantillas` | Personas encargadas y proveedores | Plantillas de liquidación, arqueo y registro de proveedor, e instrucciones |
| `01_Entrada` | Personas encargadas | Aquí dejan sus liquidaciones y arqueos |
| `02_Procesados` | Agente | Originales ya revisados, por mes |
| `03_Revisiones` | Personas encargadas y revisores | Revisión de cada archivo: lista de verificación, factura por factura, hallazgos |
| `04_Rechazados` | Personas encargadas | Archivos ilegibles, con una nota de por qué |
| `05_Dashboard` | Revisores | Acceso directo al dashboard publicado (con registro obligatorio) |
| `06_Informes` | Administración | Informe consolidado de incumplimientos de todas las unidades |
| `07_Proveedores` | Proveedores | `00_Registro`, `01_PDF`, `02_XML`, `03_Respuesta_Hacienda`; el agente archiva en `04_Conciliados` |

## Las páginas

| Página | Quién la usa | Qué hace |
|---|---|---|
| **Portal web** (Railway, `portal_web/`) | Proveedores externos; superadministrador | **Dashboard de caja chica** (`/admin/tablero`, con registro de revisión, validación de evidencia y vigencia en Postgres; lo alimenta `run.py publicar-web`) y portal de proveedores con registro y contraseña: el proveedor envía PDF + XML + respuesta de Hacienda, el servidor los verifica al instante y los guarda en Google Drive (año, mes, proveedor, factura). El superadministrador aprueba registros, decide cada factura, descarga archivos, ve la bitácora y puede ver el portal como cualquier proveedor. Despliegue: [portal_web/DESPLIEGUE_RAILWAY.md](portal_web/DESPLIEGUE_RAILWAY.md). |
| **Dashboard de revisión** | Revisores, jefaturas, auditoría | Exige registrarse (rol y motivo) antes de ver datos. Muestra gasto, hallazgos, entregas por unidad y arqueos; permite validar evidencia, decidir sobre comprobantes y confirmar que la información está al día. Dueño y editores ven la bitácora y la descargan. |
| **Portal de proveedores** | Proveedores; dueño y editores con vista administrador | No lleva datos internos. El proveedor se registra y envía PDF + XML + respuesta con verificación inmediata, y ve el estado de cada factura. El administrador alterna a su vista: aprueba registros y descarga lo recibido. |

El dashboard y el portal de claude.ai solo admiten escritura a personas de la organización con permiso de
Colaborador; los proveedores externos usan el portal web de Railway.

## Qué revisa (Reglamento de Cajas Chicas de la UNA)

Cada liquidación y cada arqueo recibe una **lista de verificación** con estado CUMPLE / NO CUMPLE / NO SE
PUEDE VERIFICAR / NO APLICA por artículo, y cada hallazgo una **gravedad sugerida** (arts. 20–22, con
reincidencia en 3 meses). La valoración final de las faltas corresponde a los órganos competentes (art. 23).

**Cada factura** (art. 6 d): a nombre de la Universidad Nacional, clave de 50 dígitos de Hacienda (fecha,
emisor y consecutivo coinciden con lo digitado), no tiquete, código IFE, IVA y aritmética, fechas dentro del
período, categoría autorizada, compras prohibidas (inmuebles, equipo de transporte, licor…), aval de UTE
(arts. 7, 7 bis, 7 ter), retención del 2 %, gastos en el extranjero (art. 10), aprobador autorizado, conflicto
de interés y cruce contra el XML y la respuesta de Hacienda del proveedor.

**Duplicados**: misma clave o mismo proveedor y número (dentro del archivo y contra todo el histórico),
posibles duplicados y compras repetidas.

**Por liquidación**: decisión inicial firmada (art. 6 c), fragmentación (arts. 3 y 6 a), monto solicitado vs.
facturas y fondo (art. 12 c), reintegro al 5.º día hábil y calendario de cierre, estado de cuenta y devolución
en liquidaciones finales, conciliación contra movimientos bancarios (art. 11 h).

**Arqueos**: concordancia de fondo, efectivo, vales y justificantes (art. 12 c), faltantes cubiertos el mismo
día y sobrantes al día hábil siguiente, vales en 5 días hábiles, arqueo sin previo aviso hecho por la persona
responsable o el PGF, y facturas del arqueo que ya fueron reintegradas.

**Apertura y catálogo** (arts. 4, 5, 13 b): una caja por FUC, una caja por persona encargada y fondo de
hasta el 10 % del monto de licitación reducida.

Los parámetros que fija cada año el Programa de Gestión Financiera (monto de licitación reducida, calendario
de cierre, monto desde el que aplica la retención) se completan en `config/politica.yaml`; mientras falten,
esos controles salen como NO SE PUEDE VERIFICAR.

## Comandos

```bash
.venv/bin/python run.py iniciar                   # carpetas del repositorio, plantillas y catálogo vacío
.venv/bin/python run.py procesar                  # cruza proveedores, revisa 01_Entrada, actualiza el dashboard
.venv/bin/python run.py informe 30                # informe consolidado (o: informe 2026-09-01 2026-09-30)
.venv/bin/python run.py resumen 7                 # datos del período para el análisis ejecutivo (JSON)
.venv/bin/python run.py proveedores               # solo el cruce de comprobantes de 07_Proveedores
.venv/bin/python run.py portal                    # genera el portal de proveedores
.venv/bin/python run.py importar-web              # trae las facturas nuevas del portal web (Railway)
.venv/bin/python run.py importar-portal <carpeta> # trae los envíos exportados del portal de claude.ai
.venv/bin/python run.py dashboard                 # solo regenera el dashboard
.venv/bin/python run.py respaldo-pendiente        # qué falta respaldar en Drive y en qué carpeta
.venv/bin/python run.py respaldo-local <carpeta>  # copia lo pendiente a Google Drive para escritorio
.venv/bin/python run.py respaldo-bitacora <dir>   # bitácora exportada → CSV
.venv/bin/python run.py demo                      # datos de demostración
```

## Prueba rápida con datos de demostración

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py demo        # 7 cajas (FUC), 4 liquidaciones/arqueos y 7 comprobantes con irregularidades sembradas
.venv/bin/python run.py procesar    # cruza, revisa y genera las revisiones y el dashboard
.venv/bin/python run.py informe 60  # informe consolidado de incumplimientos
```

Los resultados quedan en `repositorio/03_Revisiones`, `repositorio/06_Informes` y `reportes/`. El
dashboard y el portal exigen identificar a la persona, por lo que solo funcionan publicados en claude.ai;
abiertos como archivo local muestran el aviso de acceso.

## Puesta en marcha

1. Copie `config/politica.ejemplo.yaml` a `config/politica.yaml` y complete los datos de la institución y
   los parámetros del PGF. La copia real queda fuera de git, igual que el catálogo, el registro de
   proveedores, la base de datos, las liquidaciones y los identificadores de Drive.
2. Complete `config/Catalogo_Cajas.xlsx` (lo crea `run.py iniciar`) con las 120 cajas.
3. Apunte `repositorio` en `politica.yaml` a la carpeta compartida y ejecute `run.py iniciar`.
4. Comparta una carpeta de entrada por FUC con cada persona encargada, para que nadie vea las
   liquidaciones de otra unidad.
5. Publique el dashboard y el portal (Claude lo hace y guarda los enlaces en `politica.yaml`) y
   compártalos con permiso de Colaborador solo con las personas que deben usarlos.
6. Instale Google Drive para escritorio para que el respaldo en "Caja Chica U" sea automático.
7. Cada semana: pídale a Claude "procesa la semana": trae los envíos del portal, procesa, publica el
   dashboard, hace el análisis de auditor y respalda en Drive.

Para borrar los datos de demostración: elimine `data/`, `reportes/`, el contenido de `repositorio/`,
`config/Catalogo_Cajas.xlsx` y `config/Proveedores.xlsx`, y deje vacío `dashboard.aviso`.
