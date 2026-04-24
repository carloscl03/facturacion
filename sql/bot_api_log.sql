-- =====================================================================
-- bot_api_log: historial permanente de payloads enviados desde el bot
-- a las APIs de PHP (ws_venta.php / ws_compra.php) y SUNAT, con su
-- respuesta y resultado.
--
-- Una fila por cada llamada a una API. Si la operación implica varias
-- llamadas (ej: registrar venta + emitir SUNAT), genera 2 filas con el
-- mismo wa_id y created_at cercanos, distinguibles por api_destino.
--
-- Flujo del bot:
--   - Estados 0 → 5 corren en Redis (efímero, ~24h TTL)
--   - Al finalizar (estado 5) se hace POST a la API correspondiente
--   - Inmediatamente después se escribe una fila aquí con el payload
--     enviado, la respuesta y el resultado clasificado
-- =====================================================================

CREATE TABLE bot_api_log (
    -- Identidad
    id                  SERIAL          PRIMARY KEY,
    wa_id               VARCHAR(32)     NOT NULL,
    id_from             INTEGER         NOT NULL,
    id_empresa          INTEGER         NULL,

    -- Qué API se llamó
    api_destino         VARCHAR(32)     NOT NULL
        CHECK (api_destino IN ('php_venta', 'php_compra', 'sunat')),
    operacion           VARCHAR(16)     NOT NULL
        CHECK (operacion IN ('venta', 'compra')),

    -- Contexto de negocio (denormalizado para no cruzar tablas al consultar)
    tipo_documento      VARCHAR(32)     NULL,
    id_tipo_comprobante INTEGER         NULL,
    serie               VARCHAR(8)      NULL,
    numero              INTEGER         NULL,
    entidad_nombre      VARCHAR(255)    NULL,
    entidad_numero      VARCHAR(20)     NULL,
    entidad_id          INTEGER         NULL,
    moneda              VARCHAR(8)      NULL,
    id_moneda           INTEGER         NULL,

    -- Montos (alineados con el contrato precalculado: base→IGV→total)
    -- monto_total = SUM(detalle.valor_total_item) — debe coincidir con Venta.monto
    monto_base          NUMERIC(14, 2)  NULL,
    monto_igv           NUMERIC(14, 2)  NULL,
    monto_total         NUMERIC(14, 2)  NULL,

    -- Opciones (estado 4)
    id_sucursal         INTEGER         NULL,
    id_forma_pago       INTEGER         NULL,
    id_medio_pago       INTEGER         NULL,
    id_centro_costo     INTEGER         NULL,
    metodo_pago         VARCHAR(16)     NULL,    -- 'contado'/'credito'
    dias_credito        INTEGER         NULL,
    nro_cuotas          INTEGER         NULL,

    -- Resultado de la llamada
    http_status         INTEGER         NULL,    -- 200, 400, 500, etc.
    resultado           VARCHAR(16)     NOT NULL
        CHECK (resultado IN ('exitoso', 'fallido')),

    -- tipo_falla mapea con errores conocidos del SP y de SUNAT
    tipo_falla          VARCHAR(32)     NULL
        CHECK (tipo_falla IS NULL OR tipo_falla IN (
            'timeout',
            'http_error',
            'api_error',
            'sunat_rechazo',
            'moneda_invalida',          -- sp: p_id_moneda inválido
            'sin_productos',            -- sp: detalle vacío
            'producto_no_encontrado',   -- sp: id_inventario no existe
            'stock_insuficiente',       -- sp: paquete o producto sin stock
            'credenciales_invalidas',   -- API key SUNAT inválida
            'payload_invalido',         -- 400 con campos faltantes
            'error_sql',                -- excepción genérica del SP
            'error_desconocido'
        )),
    error_mensaje       TEXT            NULL,    -- p_resultado del SP o detalle del error

    -- Resultado exitoso (cuando aplica)
    id_venta            INTEGER         NULL,    -- p_venta_id del SP
    id_compra           INTEGER         NULL,
    serie_numero        VARCHAR(32)     NULL,    -- ej: 'F001-00123'
    pdf_url             VARCHAR(500)    NULL,
    sunat_estado        VARCHAR(32)     NULL,    -- 'ACEPTADA', 'RECHAZADA', etc.

    -- Performance y reintentos
    latency_ms          INTEGER         NULL,
    intento_numero      SMALLINT        NOT NULL DEFAULT 1,

    -- Payload completo enviado (para reconstrucción exacta del request)
    payload_enviado     JSONB           NULL,

    -- Respuesta cruda de la API (JSON completo, incluyendo trace si hubo error)
    respuesta_api       JSONB           NULL,

    -- Metadata extra opcional (igv_incluido, flags raros, contexto IA, etc.)
    metadata            JSONB           NULL,

    -- Timestamps
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Índices para consultas frecuentes
CREATE INDEX idx_bot_api_log_wa_id            ON bot_api_log (wa_id);
CREATE INDEX idx_bot_api_log_id_from          ON bot_api_log (id_from);
CREATE INDEX idx_bot_api_log_created_at       ON bot_api_log (created_at DESC);
CREATE INDEX idx_bot_api_log_resultado        ON bot_api_log (resultado);
CREATE INDEX idx_bot_api_log_api_destino      ON bot_api_log (api_destino);
CREATE INDEX idx_bot_api_log_id_venta         ON bot_api_log (id_venta) WHERE id_venta IS NOT NULL;
CREATE INDEX idx_bot_api_log_id_compra        ON bot_api_log (id_compra) WHERE id_compra IS NOT NULL;
CREATE INDEX idx_bot_api_log_entidad_numero   ON bot_api_log (entidad_numero);
CREATE INDEX idx_bot_api_log_tipo_falla       ON bot_api_log (tipo_falla) WHERE tipo_falla IS NOT NULL;


-- =====================================================================
-- bot_api_log_detalle: una fila por cada producto enviado en el payload.
-- Permite consultar por producto sin parsear el JSONB.
--
-- Los valores corresponden al contrato precalculado del bot:
--   precio_unitario     = base sin IGV (alta precisión, hasta 10dp)
--   valor_subtotal_item = round(precio_unitario × cantidad, 2)
--   valor_igv           = round(subtotal × 0.18, 2)
--   valor_total_item    = subtotal + igv (con IGV)
-- =====================================================================

CREATE TABLE bot_api_log_detalle (
    id                      SERIAL          PRIMARY KEY,
    log_id                  INTEGER         NOT NULL
        REFERENCES bot_api_log (id) ON DELETE CASCADE,

    -- Identificación del producto
    nombre                  VARCHAR(255)    NOT NULL,
    id_inventario           INTEGER         NULL,
    id_catalogo             INTEGER         NULL,
    id_tipo_producto        INTEGER         NULL,
    id_unidad               INTEGER         NULL,

    -- Valores del item (mismos campos que DetalleItem_Venta)
    cantidad                NUMERIC(14, 4)  NOT NULL,
    precio_unitario         NUMERIC(14, 10) NOT NULL,    -- base sin IGV, alta precisión SUNAT
    valor_subtotal_item     NUMERIC(14, 2)  NOT NULL,
    valor_igv               NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    valor_total_item        NUMERIC(14, 2)  NOT NULL,

    -- Posición original en el detalle (para reconstrucción ordenada)
    indice                  SMALLINT        NOT NULL
);

CREATE INDEX idx_bot_api_log_detalle_log_id       ON bot_api_log_detalle (log_id);
CREATE INDEX idx_bot_api_log_detalle_id_catalogo  ON bot_api_log_detalle (id_catalogo) WHERE id_catalogo IS NOT NULL;
CREATE INDEX idx_bot_api_log_detalle_nombre       ON bot_api_log_detalle (nombre);


-- =====================================================================
-- Comentarios para documentar las tablas en la DB
-- =====================================================================
COMMENT ON TABLE bot_api_log IS
    'Historial permanente de llamadas a APIs (PHP venta/compra y SUNAT) hechas por el bot. Una fila por llamada.';
COMMENT ON COLUMN bot_api_log.api_destino IS
    'Identifica a qué API se llamó. Una operación completa puede generar varias filas (ej: php_venta + sunat).';
COMMENT ON COLUMN bot_api_log.payload_enviado IS
    'JSON completo del POST enviado a la API. Permite reconstrucción exacta sin depender de bot_api_log_detalle.';
COMMENT ON COLUMN bot_api_log.respuesta_api IS
    'JSON crudo de la respuesta. Incluye trace y details cuando hubo error.';
COMMENT ON COLUMN bot_api_log.intento_numero IS
    'Número de intento (1=primera vez, 2=reintento tras corrección, etc.). Detecta correcciones del usuario.';
COMMENT ON COLUMN bot_api_log.tipo_falla IS
    'Categoría de la falla. Mapea con errores conocidos de sp_registrar_venta y de la API SUNAT.';
COMMENT ON COLUMN bot_api_log.monto_total IS
    'Total con IGV. Debe coincidir con SUM(bot_api_log_detalle.valor_total_item) y con Venta.monto del SP.';

COMMENT ON TABLE bot_api_log_detalle IS
    'Productos enviados en el payload de cada llamada. Permite consultar por producto y reconstruir el detalle.';
COMMENT ON COLUMN bot_api_log_detalle.precio_unitario IS
    'Precio base sin IGV con alta precisión (hasta 10dp). Mismo formato que detalle_items[].precio_unitario.';
COMMENT ON COLUMN bot_api_log_detalle.valor_total_item IS
    'Total del item con IGV. SUM por log_id debe coincidir con bot_api_log.monto_total.';
