"""Obtiene el refresh token de Google Drive para el portal (se ejecuta una sola vez, en su computadora).

1. En Google Cloud Console: cree un proyecto, habilite "Google Drive API", configure la pantalla de
   consentimiento (tipo Externo, agregue su correo como usuario de prueba y publíquela en Producción para que
   el token no venza a los 7 días) y cree un "ID de cliente de OAuth" de tipo "App de escritorio".
   Descargue el JSON.
2. pip install google-auth-oauthlib
3. python portal_web/obtener_token_google.py ruta/al/client_secret.json
4. Inicie sesión con la cuenta dueña de "Caja Chica U" y copie los tres valores que se imprimen a las
   variables de Railway. No los guarde en el repositorio.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

if len(sys.argv) != 2:
    sys.exit(__doc__)
flujo = InstalledAppFlow.from_client_secrets_file(sys.argv[1], scopes=["https://www.googleapis.com/auth/drive"])
cred = flujo.run_local_server(port=0, prompt="consent", access_type="offline")
datos = json.load(open(sys.argv[1]))
cliente = datos.get("installed") or datos.get("web")
print("\nCopie estas variables en Railway (Variables del servicio):\n")
print(f"GOOGLE_OAUTH_CLIENT_ID={cliente['client_id']}")
print(f"GOOGLE_OAUTH_CLIENT_SECRET={cliente['client_secret']}")
print(f"GOOGLE_OAUTH_REFRESH_TOKEN={cred.refresh_token}")
