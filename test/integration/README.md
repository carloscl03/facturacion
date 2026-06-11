# Scripts de integración

**NO son tests pytest.** Son scripts manuales que llaman APIs reales (PHP, SUNAT, Redis, WhatsApp). Crean registros, envían mensajes y/o emiten comprobantes reales.

`pytest` los ignora por default (ver `pytest.ini` raíz: `norecursedirs = test/integration`).

## Cuándo usarlos

- Validar contra producción que un endpoint sigue respondiendo
- Smoke test de un flujo completo (cliente → venta → SUNAT → PDF → WhatsApp)
- Reproducir un caso reportado por usuario

## Cómo correrlos

```bash
python test/integration/test_<nombre>.py
```

Cada script tiene su propio `if __name__ == "__main__"`.

## Cuidado

- **Crean datos reales** en BD producción
- **Envían WhatsApp reales** a los números configurados
- **Emiten facturas SUNAT** que afectan tributariamente
- Usar solo con consciencia del impacto
