import json

from prompts.plantillas import PLANTILLA_VISUAL


def build_prompt_resumen(registro: dict) -> str:
    return f"""
    Eres el Auditor de MaravIA. Genera un resumen que use la PLANTILLA VISUAL compartida. Muestra ÚNICAMENTE las líneas para las que el dato exista en el registro (no null, no vacío, no 0). Lo que no muestres irá al diagnóstico.

    DATOS EN DB (JSON):
    {json.dumps(registro, ensure_ascii=False)}

    {PLANTILLA_VISUAL}

    ### JERARQUÍA PARA EL DIAGNÓSTICO (misma que preguntador y finalizar):
    **Indispensables** (los 3 deben estar completos): 1) Monto/Detalle (monto_total > 0 o productos_json con ítems), 2) Cliente/Proveedor (entidad + documento o cliente_id/entidad_id_maestro/proveedor_id), 3) Tipo comprobante (id_comprobante_tipo definido).
    **Opcionales:** tipo_operacion, forma_pago, sucursal, centro_costo, caja_banco, fecha_emision, etc.

    ### INSTRUCCIONES:
    - Resumen: Sigue la plantilla línea a línea; incluye SOLO las líneas cuyo "mostrar si" se cumpla con DATOS EN DB. No inventes valores.
    - Usa nombres (Factura, Soles, Cliente/Proveedor), nunca IDs numéricos.
    - Diagnóstico: Lista primero los indispensables que falten (1, 2, 3), luego opcionales. **Solo escribe "✅ Listo para confirmar y emitir" si los 3 indispensables están completos.** Si falta monto/detalle, cliente/proveedor o tipo comprobante, dilo en el diagnóstico; no digas que está listo.
    - Si entidad_numero_documento tiene valor, no cuentes "RUC/DNI" como faltante de identificación.
    """
