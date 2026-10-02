# Agente de Control de Caja Chica

Este proyecto audita los **arqueos** y las **liquidaciones** de caja chica que los custodios dejan en un
repositorio compartido (OneDrive o Google Drive sincronizado en esta Mac). Tiene dos capas:

1. **Motor de reglas (Python, determinístico)**: revisa cada factura contra la política, detecta
   duplicados, fraccionamiento y descuadres de arqueo, lo registra todo en SQLite, devuelve un Excel de
   revisión al repositorio y regenera el dashboard.
2. **Claude (criterio de auditor)**: interpreta los resultados, analiza los duplicados y los patrones que
   una regla no detecta, y redacta el informe ejecutivo.

## Comandos

```bash
.venv/bin/python run.py procesar     # revisa todo lo de 01_Entrada + actualiza dashboard (salida JSON)
.venv/bin/python run.py informe 7    # informe Excel de incumplimientos de TODAS las unidades (o: informe 2026-09-01 2026-09-30)
.venv/bin/python run.py resumen 7    # datos de los últimos N días para el análisis ejecutivo (JSON)
.venv/bin/python run.py dashboard    # solo regenera el dashboard
.venv/bin/python run.py iniciar      # crea carpetas y plantillas en el repositorio
```

- Política y datos de la institución: `config/politica.yaml` (nunca poner montos ni cédulas en el código).
- Catálogo de las unidades de negocio (código, unidad, responsable, cédula, fondo, aprobadores, activa):
  `config/Catalogo_Cajas.xlsx`. Es la fuente de verdad del responsable y el monto de cada caja.
- Documentos oficiales de la política: carpeta `politicas/`.
- Base de datos: `data/cajachica.db` (tablas `liquidaciones`, `facturas`, `arqueos`, `arqueo_pendientes`, `hallazgos`).
- Dashboard: `reportes/dashboard.html` y copia en `<repositorio>/05_Dashboard/`.

## Cuando el usuario pida "procesa", "revisa lo de la semana", "corre el agente" o similar

1. Ejecutar `run.py procesar`. Si `01_Entrada` está vacía, decirlo y ofrecer `run.py resumen`.
2. Reportar archivos rechazados (no legibles) y omitidos (ya procesados) con su motivo.
3. Ejecutar `run.py resumen 7` y hacer el **análisis de auditor**, que NO se limita a repetir las reglas:
   - **Duplicados**: para cada `DUPLICADO_EXACTO` / `POSIBLE_DUPLICADO` / `PENDIENTE_YA_LIQUIDADO`,
     consultar ambas facturas en la BD y concluir: ¿error de digitación, reintento de cobro, o patrón
     (mismo custodio/proveedor repetido en varias semanas)? Cuantificar el monto en riesgo.
   - **Pertinencia del gasto**: leer las descripciones. Una descripción puede pasar las palabras clave y
     aun así no tener fin institucional (ej. "atención a visitantes" todas las semanas, compras de
     activos disfrazadas como materiales, descripciones vagas como "varios" o "compras").
   - **Patrones**: concentración en un proveedor, un solicitante que acumula hallazgos, crecimiento del
     gasto semana a semana por caja, facturas de proveedores personas físicas, fines de semana
     recurrentes, montos justo debajo del límite por factura.
   - **Arqueos**: faltantes recurrentes en la misma caja, vales que se renuevan, pendientes inflados.
4. Entregar: (a) veredicto por liquidación (reintegrar / reintegrar parcial / devolver al custodio) con el
   monto recomendado, (b) hallazgos graves con evidencia (caja, liquidación, fila, proveedor, monto),
   (c) patrones, (d) acciones recomendadas y a quién.
5. Separar siempre **hecho** (lo que dice el dato) de **inferencia** (lo que sugiere). Un duplicado es un
   hecho; que sea intencional es una inferencia que se presenta como hipótesis a verificar, nunca como
   acusación.

## Cuando el usuario entregue o pegue la política

1. Leer el documento completo (de `politicas/` o del chat).
2. Trasladar a `config/politica.yaml` todo parámetro medible: datos de la institución, límites, plazos,
   categorías permitidas, conceptos prohibidos/sensibles, tipos de comprobante, tolerancias.
3. Completar `referencias_politica` con el artículo que respalda cada regla.
4. Copiar a `reglas_cualitativas` las cláusulas que requieren criterio, textuales, con su artículo.
5. Mostrar al usuario una tabla "cláusula → cómo se controla (regla automática / revisión de Claude /
   no controlable con los datos entregados)" y pedir confirmación de lo que se interpretó.

## Cuando el usuario entregue el listado de responsables y montos

Cargarlo en `config/Catalogo_Cajas.xlsx` respetando las columnas; reportar códigos duplicados, montos
vacíos o responsables repetidos en varias cajas antes de guardar.

## Informe de incumplimientos

`run.py informe` genera el Excel consolidado (también en `<repositorio>/06_Informes/`) con: resumen,
semáforo por unidad, **documentos incumplidos** (una fila por factura: unidad, responsable, liquidación,
archivo, fila, proveedor, N° factura, clave, monto, incumplimientos, norma y acción requerida),
incumplimientos de liquidación/arqueo y unidades sin entrega. Al presentarlo, además revisar las
`reglas_cualitativas` contra las descripciones de las facturas y agregar lo encontrado, citando la fila.

## Dashboard publicado y bitácora de revisión

- Enlace oficial: `dashboard.url` en `config/politica.yaml`. El dashboard SOLO se consulta ahí: cada persona
  se registra con su cuenta (rol, motivo, alcance) antes de ver datos; fuera de claude.ai la página se bloquea.
- Después de cada `run.py procesar`, republicar `reportes/dashboard.html` con la herramienta Artifact pasando
  `url` = el enlace oficial (sin `capabilities`, para conservar las reglas). Nunca publicar en otra URL.
- Base de la página: `accesos/<persona>/meses/<AAAA-MM>` (ingresos y confirmaciones de vigencia) y
  `validaciones/<persona>/meses/<AAAA-MM>` (validación de evidencia por hallazgo, campo `clave`). Leer con
  ArtifactData (`list`) y resolver nombres con `action: "profiles"`. Nunca escribir ni borrar registros ahí:
  es la evidencia de auditoría.
- Cuando el usuario pida "quién revisó" o "qué falta validar": leer la bitácora, cruzar `clave` con
  `clave_hallazgo()` de `cajachica/dashboard.py` y reportar hallazgos ALTA/MEDIA sin validar por unidad.
- Quitar `dashboard.aviso` del yaml cuando se carguen datos reales.

## Reglas de trabajo

- No modificar hallazgos ni borrar registros de la BD sin que el usuario lo pida. Para cerrar un hallazgo:
  `UPDATE hallazgos SET estado='Cerrado', comentario='...' WHERE id=...` solo con instrucción explícita.
- Si el usuario cambia la política (límites, categorías, institución), editar `config/politica.yaml`.
- Si aparece un formato de archivo nuevo que no se reconoce, agregar los nombres de columna como alias en
  `cajachica/lectura.py` en lugar de pedir a los custodios que cambien su archivo.
- Montos en colones con separador de miles; fechas en dd/mm/aaaa.
