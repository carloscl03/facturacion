"""DEPRECATED: Reemplazado por paso_actual (0-4) en la tabla historial_cache.
Se conserva por compatibilidad con servicios legacy (analizador, confirmador, registrador)."""

INICIAL = "inicial"
PENDIENTE_TIPO_OPERACION = "pendiente_tipo_operacion"
PENDIENTE_CONFIRMACION = "pendiente_confirmacion"
PENDIENTE_IDENTIFICACION = "pendiente_identificacion"
PENDIENTE_DATOS = "pendiente_datos"
LISTO_PARA_FINALIZAR = "listo_para_finalizar"
COMPLETADO = "completado"

VALIDOS = frozenset({
    INICIAL,
    PENDIENTE_TIPO_OPERACION,
    PENDIENTE_CONFIRMACION,
    PENDIENTE_IDENTIFICACION,
    PENDIENTE_DATOS,
    LISTO_PARA_FINALIZAR,
    COMPLETADO,
})
