import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from renault_api.credential_store import FileCredentialStore
from renault_api.renault_client import RenaultClient

# URLs oficiais da Renault para a região Europeia
GIGYA_URL = "https://accounts.eu1.gigya.com"
KAMEREON_URL = "https://api-wired-prod-1-eu1.wrd-aws.com"

def load_credentials():
    """Carrega as credenciais do segredo do GitHub e prepara o ficheiro local."""
    raw = os.environ.get("RENAULT_CREDENTIALS_JSON")
    if not raw:
        raise RuntimeError("ERRO: RENAULT_CREDENTIALS_JSON não está definida.")

    credentials = json.loads(raw)
    
    # Verificar chaves essenciais (nota a grafia 'accound-id' que a biblioteca usa)
    if "accound-id" not in credentials or "vin" not in credentials:
        raise RuntimeError("ERRO: Credenciais inválidas. Faltam 'accound-id' ou 'vin'.")

    credentials_dir = Path.home() / ".credentials"
    credentials_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    credentials_file = credentials_dir / "renault-api.json"
    
    credentials_file.write_text(json.dumps(credentials), encoding="utf-8")
    credentials_file.chmod(0o600)
    
    return FileCredentialStore(str(credentials_file))

async def get_vehicle_data(credential_store):
    """Obtém apenas os dados de bateria e cockpit do veículo."""
    client = RenaultClient(
        credential_store=credential_store,
        locale="pt_PT",
        gigya_root_url=GIGYA_URL,
        kamereon_root_url=KAMEREON_URL
    )
    
    # Obter a conta associada às credenciais
    account = await client.get_api_account()
    
    # Obter o veículo associado à conta
    vehicle = await account.get_api_vehicle()
    
    # Recolher apenas os dados necessários
    battery_status = await vehicle.get_battery_status()
    cockpit_status = await vehicle.get_cockpit()
    
    return {
        "battery_level": battery_status.batteryLevel,
        "battery_autonomy": battery_status.batteryAutonomy,
        "battery_timestamp": battery_status.timestamp.isoformat() if battery_status.timestamp else None,
        "total_mileage": cockpit_status.totalMileage,
        "cockpit_timestamp": cockpit_status.timestamp.isoformat() if cockpit_status.timestamp else None
    }

async def send_to_apps_script(data):
    """Envia os dados para o Google Apps Script."""
    url = os.environ.get("APPS_SCRIPT_URL")
    secret = os.environ.get("APPS_SCRIPT_SECRET")
    
    if not url or not secret:
        raise RuntimeError("ERRO: APPS_SCRIPT_URL ou APPS_SCRIPT_SECRET não definidos.")

    payload = {
        "secret": secret,
        "data": data
    }
    
    headers = {"Content-Type": "application/json"}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                response_text = await response.text()
                print(f"Status HTTP: {response.status}")
                print(f"Resposta do Apps Script: {response_text}")
                
                if response.status != 200:
                    raise RuntimeError(f"Erro na comunicação com Apps Script: {response.status}")
                    
                return json.loads(response_text)
        except Exception as e:
            raise RuntimeError(f"Falha ao enviar dados: {str(e)}")

async def main():
    try:
        print("Iniciar recolha de dados do Dacia Spring...")
        
        # 1. Carregar credenciais
        credential_store = load_credentials()
        print("Credenciais carregadas com sucesso.")
        
        # 2. Obter dados do veículo
        data = await get_vehicle_data(credential_store)
        print(f"Dados recolhidos: Bateria={data['battery_level']}%, Autonomia={data['battery_autonomy']}km, KM={data['total_mileage']}")
        
        # 3. Enviar para Google Sheets
        result = await send_to_apps_script(data)
        
        if result.get("success"):
            print("Dados guardados com sucesso no Google Sheets!")
        else:
            print(f"Aviso: O Apps Script processou o pedido mas reportou: {result.get('message')}")
            
    except Exception as e:
        print(f"ERRO CRÍTICO: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
