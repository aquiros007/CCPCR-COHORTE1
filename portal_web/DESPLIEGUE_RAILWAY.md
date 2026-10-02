# Despliegue del portal de proveedores en Railway

El portal (`portal_web/`) es una aplicación FastAPI. Railway la arranca con el comando definido en
`railway.json` y `railpack.json`:

```
uvicorn portal_web.app:app --host 0.0.0.0 --port $PORT
```

## 1. Servicios en Railway

1. Servicio web conectado a este repositorio (rama `main`).
2. Agregue una base **PostgreSQL** al proyecto (New → Database → PostgreSQL).
3. Agregue un **volumen** al servicio web montado en `/data` (`railway volume add --mount-path /data`).
3. En el servicio web → *Settings → Networking*, genere un dominio público (o conecte el suyo).

## 2. Variables del servicio web

| Variable | Obligatoria | Valor |
|---|---|---|
| `DATABASE_URL` | Sí | `${{Postgres.DATABASE_URL}}` (referencia a la base de Railway) |
| `SECRET_KEY` | Sí | Cadena aleatoria larga, por ejemplo la salida de `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ADMIN_EMAIL` | Sí | Correo con el que entra el superadministrador |
| `ADMIN_PASSWORD` | Sí | Contraseña larga del superadministrador |
| `API_TOKEN` | Sí | Otra cadena aleatoria larga; la usa el agente (`run.py importar-web`) |
| `DRIVE_FACTURAS_FOLDER_ID` | Para Drive | Id de la carpeta `01_Facturas` dentro de "Caja Chica U" |
| `GOOGLE_OAUTH_CLIENT_ID` | Para Drive | Ver sección 3 |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Para Drive | Ver sección 3 |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | Para Drive | Ver sección 3 |
| `CAJACHICA_DATA_DIR` | Sí | `/data` (volumen persistente: base del motor, entregas, revisiones, informes) |
| `STORAGE_DIR` | Sí | `/data/portal_archivos` (facturas de proveedores si Drive no está configurado) |
| `DRIVE_RAIZ_FOLDER_ID` | Para Drive | Id de la carpeta "Caja Chica U" (respaldo de originales, revisiones, informes y configuración) |
| `INSTITUCION_NOMBRE` / `INSTITUCION_CEDULA` | No | Si difieren de `config/politica.ejemplo.yaml` |
| `MAX_PDF_MB` | No | Tamaño máximo del PDF (5 por defecto) |

Sin las variables de Google el portal funciona igual, pero guarda los archivos en el disco del servidor, que
Railway borra en cada despliegue: úselo así solo para probar.

## 3. Credencial de Google Drive

La carpeta "Caja Chica U" está en una cuenta personal de Gmail. Las cuentas de servicio de Google no tienen
espacio propio en "Mi unidad", así que el portal sube los archivos **a nombre de la cuenta dueña**, con OAuth:

1. En [Google Cloud Console](https://console.cloud.google.com): cree un proyecto y habilite **Google Drive API**.
2. *Pantalla de consentimiento de OAuth*: tipo Externo, agregue su correo y publíquela en **Producción**
   (en modo Prueba el token vence a los 7 días).
3. *Credenciales → Crear → ID de cliente de OAuth → App de escritorio*. Descargue el JSON.
4. En su computadora: `pip install google-auth-oauthlib` y
   `python portal_web/obtener_token_google.py client_secret.json`. Inicie sesión con la cuenta dueña de
   "Caja Chica U" y copie las tres variables que imprime a Railway.

Si la carpeta se mueve a una Unidad compartida de Google Workspace, puede usar en su lugar una cuenta de
servicio: `GOOGLE_SERVICE_ACCOUNT_JSON` con el JSON completo de la cuenta, agregada como miembro de la unidad.

## 4. Primer ingreso

1. Abra el dominio del servicio: `/salud` debe responder `{"ok": true, "almacen": "drive"}`.
2. Ingrese con `ADMIN_EMAIL` y `ADMIN_PASSWORD`: verá la **vista administrador**. Desde cada proveedor puede
   abrir **Ver como este proveedor**.
3. Comparta con los proveedores la dirección del portal: se registran en `/registro`.

## 5. Conexión con el agente

En la Mac donde corre el agente:

```bash
export PORTAL_WEB_URL="https://<su-dominio>"
export PORTAL_API_TOKEN="<el mismo API_TOKEN de Railway>"
.venv/bin/python run.py importar-web
```

Trae las facturas nuevas (estado Recibido) a `07_Proveedores`, las cruza, actualiza el registro de
proveedores y le muestra al proveedor el estado "En revisión".

Para publicar el dashboard de caja chica en el portal (después de cada procesamiento):

```bash
railway run --service CCPCR-COHORTE1 -- .venv/bin/python run.py publicar-web
```

## Seguridad incluida

Contraseñas con scrypt, sesiones firmadas (8 h, `HttpOnly`, `Secure` en producción), protección CSRF en
todos los formularios, límite de 5 intentos de ingreso fallidos por usuario cada 15 minutos, cabeceras de
seguridad (CSP sin scripts externos, sin iframes), XML sin DTD ni entidades, validación de tamaño y tipo de
archivo, y bitácora de registros, ingresos (también los fallidos), envíos y decisiones.
