import json

import requests


def registrar_compra():
    """
    Llama a la API de compras con el JSON de ejemplo y devuelve la respuesta.
    """

    # Endpoint correcto bajo /servicio/n8n
    url = "https://api.maravia.pe/servicio/n8n/ws_compra.php"

    payload = {
        "codOpe": "REGISTRAR_COMPRA",
        "empresa_id": 1,
        "usuario_id": 1,
        "id_proveedor": 5,
        "id_tipo_comprobante": 1,
        "fecha_emision": "2025-10-31",
        "nro_documento": "F001-00001",
        "id_medio_pago": 1,
        "id_forma_pago": 1,
        "id_moneda": 1,
        "id_sucursal": 1,
        "tipo_compra": "Contado",
        "dias_credito": 30,
        "cuotas": 3,
        "porcentaje_detraccion": 0,
        "fecha_pago": "2025-11-15",
        "fecha_vencimiento": "2025-11-30",
        "enlace_documento": "https://storage.maravia.pe/compras/doc123.pdf",
        "id_tipo_afectacion": 1,
        "observacion": "Compra de productos para stock",
        "id_caja_banco": 1,
        "id_centro_costo": 1,
        "id_tipo_compra_gasto": 1,
        "detalles": [
            {
                "id_inventario": None,
                "id_catalogo": 10,
                "id_tipo_producto": 1,
                "cantidad": 5,
                "id_unidad": 1,
                "precio_unitario": 100,
                "concepto": "Producto X",
                "valor_subtotal_item": 500,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": 90,
                "valor_icbper": 0,
                "valor_total_item": 590,
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        ],
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    return response


def test_registrar_compra():
    """
    Test para usar con pytest, por si lo necesitas.
    """
    response = registrar_compra()
    print("Status code:", response.status_code)
    print("Response text:", response.text)
    assert response.status_code in (200, 201)


if __name__ == "__main__":
    try:
        resp = registrar_compra()
        print("Status code:", resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            print("Respuesta no es JSON válido:")
            print(resp.text)
        else:
            print("Respuesta JSON:", json.dumps(data, indent=2, ensure_ascii=False))
            if data.get("success") is True:
                print("Compra registrada. id_compra:", data.get("id_compra"))
            elif "error" in data:
                print("Error al registrar compra:", data.get("error"))
                if data.get("details"):
                    print("Detalles:", data["details"])
    except Exception as e:
        print("Error al llamar a la API:", e)

