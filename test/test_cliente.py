import requests
import json

URL_CLIENTE = "https://api.maravia.pe/servicio/n8n/ws_cliente.php"
URL_PROVEEDOR = "https://api.maravia.pe/servicio/n8n_asistente/ws_proveedor.php"
ID_EMPRESA = 2

# Mapeo completo de datos para testear
DATOS_PARA_PROBAR = {
    "ARIEL / CENCOSUD": [
        ("RUC", "20109072177"),
        ("DNI", "74599333"),
        ("Nombre", "Ariel Amado Frias"),
        ("Razón Social", "CENCOSUD RETAIL PERÚ S.A."),
        ("Comercial", "Metro"),
        ("Teléfono", "5933511222")
    ],
    "JOSÉ / GLOBAL": [
        ("DNI", "85274196"),
        ("RUC", "20123456789"),
        ("Razón Social", "Importaciones Global EIRL"),
        ("Comercial", "Global Import"),
        ("Teléfono", "988776655")
    ]
}

def test_exhaustivo():
    for sujeto, campos in DATOS_PARA_PROBAR.items():
        print(f"\n🚀 PROBANDO DATOS DE: {sujeto}")
        print(f"{'Campo':<15} | {'Valor':<30} | {'CLI':<5} | {'PROV':<5}")
        print("-" * 65)
        
        for etiqueta, valor in campos:
            # 1. Test Cliente
            try:
                r_cli = requests.get(URL_CLIENTE, params={"codOpe": "BUSCAR_CLIENTE", "empresa_id": ID_EMPRESA, "termino": valor})
                found_cli = "✅" if r_cli.json().get('found') else "❌"
            except: found_cli = "💥"

            # 2. Test Proveedor
            try:
                payload = {"codOpe": "BUSCAR_PROVEEDOR", "id_empresa": ID_EMPRESA, "nombre_completo": valor}
                r_prov = requests.post(URL_PROVEEDOR, json=payload)
                found_prov = "✅" if r_prov.json().get('found') else "❌"
            except: found_prov = "💥"

            print(f"{etiqueta:<15} | {valor:<30} | {found_cli:<5} | {found_prov:<5}")

if __name__ == "__main__":
    test_exhaustivo()