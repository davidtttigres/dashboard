import os
import json

# Script para verificar las credenciales
env_creds = os.environ.get('GOOGLE_CREDENTIALS_JSON')

if env_creds:
    print("✅ Variable de entorno GOOGLE_CREDENTIALS_JSON encontrada")
    try:
        creds_dict = json.loads(env_creds)
        print(f"\n📧 Email de la cuenta de servicio:")
        print(f"   {creds_dict.get('client_email', 'NO ENCONTRADO')}")
        print(f"\n🆔 Project ID:")
        print(f"   {creds_dict.get('project_id', 'NO ENCONTRADO')}")
        print(f"\n🔑 Campos presentes en el JSON:")
        for key in creds_dict.keys():
            print(f"   - {key}")
    except json.JSONDecodeError as e:
        print(f"❌ Error al parsear el JSON: {e}")
        print(f"\nPrimeros 100 caracteres del contenido:")
        print(env_creds[:100])
else:
    print("❌ Variable de entorno GOOGLE_CREDENTIALS_JSON NO encontrada")
    print("\nBuscando archivo local...")
    credentials_path = os.path.join(os.path.dirname(__file__), '../credentials/credentials.json')
    if os.path.exists(credentials_path):
        print(f"✅ Archivo encontrado en: {credentials_path}")
        with open(credentials_path, 'r') as f:
            creds_dict = json.load(f)
            print(f"\n📧 Email de la cuenta de servicio:")
            print(f"   {creds_dict.get('client_email', 'NO ENCONTRADO')}")
    else:
        print(f"❌ Archivo no encontrado en: {credentials_path}")
