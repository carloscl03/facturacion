<?php
/**
 * API REST para N8N - Servicio de Envío de WhatsApp (API Oficial Cloud)
 *
 * Este servicio permite enviar mensajes de WhatsApp a través de la API oficial de Meta.
 *
 * Endpoint: /servicio/n8n/ws_send_whatsapp_oficial.php
 * Método: POST
 *
 * FORMATOS SOPORTADOS:
 *
 * 1. JSON con id_empresa (RECOMENDADO - obtiene credenciales de la BD):
 * {
 *   "id_empresa": 1,
 *   "phone": "51980253258",
 *   "message": "Hola, este es un mensaje de prueba",
 *   "type": "text"
 * }
 *
 * 2. JSON con credenciales directas (legacy):
 * {
 *   "access_token": "TOKEN_DE_WHATSAPP",
 *   "phone_number_id": "ID_NUMERO_TELEFONO",
 *   "phone": "51980253258",
 *   "message": "Hola, este es un mensaje de prueba",
 *   "type": "text"
 * }
 *
 * 3. Form-Data (Content-Type: application/x-www-form-urlencoded):
 * id_empresa=1&phone=51980253258&message=Hola
 *
 * Parámetros:
 * - id_empresa: ID de la empresa (obtiene credenciales de configuracion_whatsapp_api)
 * - access_token: Token de acceso (opcional si se proporciona id_empresa)
 * - phone_number_id: ID del número de teléfono (opcional si se proporciona id_empresa)
 * - phone: Número de teléfono destino (REQUERIDO)
 * - message: Mensaje a enviar (requerido para tipo texto)
 * - type: Tipo de mensaje (text, image, document, audio, video). Por defecto: text
 *
 * Respuesta exitosa:
 * {
 *   "success": true,
 *   "message": "Mensaje enviado correctamente",
 *   "response": {...}
 * }
 *
 * Respuesta de error:
 * {
 *   "success": false,
 *   "error": "Descripción del error",
 *   "details": "Detalles adicionales"
 * }
 */

// Capturar errores fatales y convertirlos en JSON (excepto deprecaciones)
set_error_handler(function($severity, $message, $file, $line) {
    // Ignorar deprecaciones (E_DEPRECATED = 8192)
    if ($severity === E_DEPRECATED || $severity === E_USER_DEPRECATED) {
        return true; // No lanzar excepción para deprecaciones
    }
    throw new ErrorException($message, 0, $severity, $file, $line);
});

register_shutdown_function(function() {
    $error = error_get_last();
    if ($error !== null && in_array($error['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR])) {
        http_response_code(500);
        echo json_encode([
            'success' => false,
            'error' => 'Error fatal en el servidor',
            'details' => $error['message'],
            'file' => basename($error['file']),
            'line' => $error['line']
        ]);
    }
});

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With');
header('Access-Control-Allow-Credentials: true');
header('Access-Control-Max-Age: 86400');

// Manejar preflight OPTIONS request
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

// Incluir conexión a base de datos
require_once '../conexion.php';

// Configuración de WhatsApp Cloud API
define('GRAPH_API_VERSION', 'v21.0');
define('GRAPH_API_URL', 'https://graph.facebook.com/' . GRAPH_API_VERSION);

// Credenciales de Maravia para Coexistence (plataforma 1 - Embedded Signup)
// Estas credenciales se usan primero para empresas que usan coexistence
define('MARAVIA_PHONE_NUMBER_ID', getenv('MARAVIA_PHONE_NUMBER_ID') ?: '546aborrar78893433');
define('MARAVIA_ACCESS_TOKEN', getenv('MARAVIA_ACCESS_TOKEN') ?: 'EAAQFs6SYPWIBQeqI6SmhXdwHLBHhFfOAbAqcU3aZBjbKuRpfo7MKK8ZAtYOPW1DhofhL7DoUFqb4hNwXGOYD63R0zBVbi5gvFaVZBLHhfglBhJvczk4KoLxLFA2V1hoFPbPZCkYBgihdZBaCJZA7sujWqnpyb2gcpJ2vx3HY1b05f356ftdfOI28Cd0hyvN1zSOAZDZD');
define('MARAVIA_APP_SECRET', getenv('MARAVIA_APP_SECRET') ?: '4c7ac78borrar619bbbb224c66c1189c3');

/**
 * Obtiene las credenciales de Maravia (coexistence)
 * @return array Credenciales de Maravia
 */
function obtenerCredencialesMaravia() {
    return [
        'id_empresa' => 0, // Maravia principal
        'id_plataforma' => 1, // Embedded Signup
        'numero_telefono_id' => MARAVIA_PHONE_NUMBER_ID,
        'token_whatsapp' => MARAVIA_ACCESS_TOKEN,
        'clave_secreta' => MARAVIA_APP_SECRET,
        'app_id' => null
    ];
}

/**
 * Obtiene las credenciales de WhatsApp desde la BD según el id_empresa o dni_asociado
 * @param int $idEmpresa El ID de la empresa
 * @param string|null $dniAsociado DNI asociado (para plataforma NDIAL)
 * @return array|null Credenciales o null si no se encuentra
 */
function obtenerCredencialesPorEmpresa($idEmpresa, $dniAsociado = null, $idPlataforma = null) {
    try {
        $conexion = new Conexion();
        $pdo = $conexion->conectar();

        if (!$pdo) {
            error_log("❌ No se pudo conectar a la BD para obtener credenciales");
            return null;
        }

        // Si se proporciona dni_asociado, buscar por ese campo (NDIAL)
        if (!empty($dniAsociado)) {
            $sql = "SELECT
                        id_empresa,
                        id_plataforma,
                        numero_telefono_id,
                        token_whatsapp,
                        clave_secreta,
                        app_id
                    FROM configuracion_whatsapp_api
                    WHERE dni_asociado = :dni_asociado
                    AND estado_registro = 1";

            if (!empty($idPlataforma)) {
                $sql .= " AND id_plataforma = :id_plataforma";
            }

            $sql .= " LIMIT 1";

            $stmt = $pdo->prepare($sql);
            $stmt->bindParam(':dni_asociado', $dniAsociado);
            if (!empty($idPlataforma)) {
                $stmt->bindParam(':id_plataforma', $idPlataforma, PDO::PARAM_INT);
            }
            $stmt->execute();
        } else {
            // Buscar credenciales activas para la empresa
            $sql = "SELECT
                        id_empresa,
                        id_plataforma,
                        numero_telefono_id,
                        token_whatsapp,
                        clave_secreta,
                        app_id
                    FROM configuracion_whatsapp_api
                    WHERE id_empresa = :id_empresa
                    AND estado_registro = 1";

            if (!empty($idPlataforma)) {
                $sql .= " AND id_plataforma = :id_plataforma";
            }

            $sql .= " ORDER BY id_plataforma ASC
                    LIMIT 1";

            $stmt = $pdo->prepare($sql);
            $stmt->bindParam(':id_empresa', $idEmpresa, PDO::PARAM_INT);
            if (!empty($idPlataforma)) {
                $stmt->bindParam(':id_plataforma', $idPlataforma, PDO::PARAM_INT);
            }
            $stmt->execute();
        }

        $result = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($result) {
            error_log("✅ Credenciales encontradas para id_empresa: $idEmpresa, dni_asociado: $dniAsociado, id_plataforma: $idPlataforma -> Plataforma: {$result['id_plataforma']}");
            return $result;
        }

        error_log("⚠️ No se encontraron credenciales para id_empresa: $idEmpresa, dni_asociado: $dniAsociado, id_plataforma: $idPlataforma");
        return null;

    } catch (Exception $e) {
        error_log("❌ Error al obtener credenciales: " . $e->getMessage());
        return null;
    }
}

// Obtener parámetros según el método HTTP
$contentType = $_SERVER['CONTENT_TYPE'] ?? '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $rawInput = file_get_contents('php://input');
    // Intentar decodificar como JSON primero
    $data = json_decode($rawInput, true);
    // Si no es JSON válido, verificar si es form-data
    if ($data === null && !empty($rawInput)) {
        parse_str($rawInput, $data);
    }
    // Si aún no hay datos, intentar con $_POST
    if (empty($data)) {
        $data = $_POST;
    }
} else if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $data = $_GET;
} else {
    http_response_code(405);
    echo json_encode(['error' => 'Método no permitido. Use POST o GET']);
    exit;
}

// Si después de todo no hay datos, error
if (empty($data)) {
    http_response_code(400);
    echo json_encode([
        'error' => 'Datos inválidos o vacíos',
        'details' => 'Envíe los datos como JSON, form-data o query string',
        'content_type' => $contentType,
        'method' => $_SERVER['REQUEST_METHOD']
    ]);
    exit;
}

// Validar campos requeridos
$id_empresa = $data['id_empresa'] ?? $data['EmpresaId'] ?? ''; // Soporta ambos nombres
$dni_asociado = $data['dni_asociado'] ?? '';
$access_token = $data['access_token'] ?? '';
$phone_number_id = $data['phone_number_id'] ?? '';
$phone = $data['phone'] ?? '';
$message = $data['message'] ?? '';
$type = $data['type'] ?? 'text'; // Por defecto texto
$id_plataforma = $data['id_plataforma'] ?? '';

// Campos específicos para cada tipo
$image_url = $data['image_url'] ?? '';
$document_url = $data['document_url'] ?? '';
$filename = $data['filename'] ?? '';
$audio_url = $data['audio_url'] ?? '';
$video_url = $data['video_url'] ?? '';

// Si se proporciona id_empresa o dni_asociado, obtener credenciales de la BD
if (!empty($id_empresa) || !empty($dni_asociado)) {
    $credenciales = obtenerCredencialesPorEmpresa($id_empresa, $dni_asociado, !empty($id_plataforma) ? (int)$id_plataforma : null);

    if (!$credenciales) {
        http_response_code(404);
        echo json_encode([
            'success' => false,
            'error' => 'No se encontraron credenciales de WhatsApp para la empresa',
            'id_empresa' => $id_empresa
        ]);
        exit;
    }

    $idPlataforma = $credenciales['id_plataforma'] ?? null;

    // El phone_number_id siempre es el de la empresa
    $phone_number_id = $credenciales['numero_telefono_id'];

    // Para plataformas con Coexistence (1 = Embedded Signup, 5 = NDIAL), usar token de Maravia
    if ($idPlataforma == 1 || $idPlataforma == 5) {
        // Verificar que el token de Maravia esté configurado
        if (!empty(MARAVIA_ACCESS_TOKEN)) {
            $access_token = MARAVIA_ACCESS_TOKEN;
            error_log("📱 Usando token de MARAVIA (coexistence) para empresa: $id_empresa (plataforma: $idPlataforma, phone_number_id: $phone_number_id)");
        } else {
            // Fallback a token de la empresa si Maravia no está configurado
            $access_token = $credenciales['token_whatsapp'];
            error_log("⚠️ Token de Maravia no configurado, usando token de BD para empresa: $id_empresa");
        }
    } else {
        // Otras plataformas: usar token de la BD directamente
        $access_token = $credenciales['token_whatsapp'];
        error_log("📱 Usando credenciales de BD para empresa: $id_empresa (plataforma: $idPlataforma)");
    }
}

// Validar que tengamos las credenciales (ya sea de BD o directas)
if (empty($access_token)) {
    http_response_code(400);
    echo json_encode([
        'success' => false,
        'error' => 'Token de acceso no disponible',
        'details' => 'Proporcione id_empresa o access_token directamente'
    ]);
    exit;
}

if (empty($phone_number_id)) {
    http_response_code(400);
    echo json_encode([
        'success' => false,
        'error' => 'ID del número de teléfono no disponible',
        'details' => 'Proporcione id_empresa o phone_number_id directamente'
    ]);
    exit;
}

if (empty($phone)) {
    http_response_code(400);
    echo json_encode(['error' => 'Número de teléfono requerido']);
    exit;
}

// El mensaje solo es obligatorio para tipo texto
if ($type === 'text' && empty($message)) {
    http_response_code(400);
    echo json_encode(['error' => 'Mensaje requerido para tipo texto']);
    exit;
}

// Validaciones específicas por tipo
switch ($type) {
    case 'text':
        if (empty($message)) {
            http_response_code(400);
            echo json_encode(['error' => 'Mensaje de texto requerido']);
            exit;
        }
        break;

    case 'image':
        if (empty($image_url)) {
            http_response_code(400);
            echo json_encode(['error' => 'URL de imagen requerida para tipo imagen']);
            exit;
        }
        break;

    case 'document':
        if (empty($document_url)) {
            http_response_code(400);
            echo json_encode(['error' => 'URL de documento requerida para tipo documento']);
            exit;
        }
        if (empty($filename)) {
            http_response_code(400);
            echo json_encode(['error' => 'Nombre de archivo requerido para tipo documento']);
            exit;
        }
        break;

    case 'audio':
        if (empty($audio_url)) {
            http_response_code(400);
            echo json_encode(['error' => 'URL de audio requerida para tipo audio']);
            exit;
        }
        break;

    case 'video':
        if (empty($video_url)) {
            http_response_code(400);
            echo json_encode(['error' => 'URL de video requerida para tipo video']);
            exit;
        }
        break;

    default:
        http_response_code(400);
        echo json_encode(['error' => 'Tipo de mensaje no válido. Use: text, image, document, audio, video']);
        exit;
}

/**
 * Formatear número de teléfono para WhatsApp Cloud API
 * Debe incluir código de país sin el símbolo +
 */
function formatearNumeroTelefono($phone) {
    // Eliminar espacios, guiones y paréntesis
    $phone = preg_replace('/[\s\-\(\)\+]/', '', $phone);

    // Si empieza con 0, quitarlo
    if (strpos($phone, '0') === 0) {
        $phone = substr($phone, 1);
    }

    // Si no tiene código de país (menos de 11 dígitos para Perú), agregar 51
    if (strlen($phone) <= 9) {
        $phone = '51' . $phone;
    }

    return $phone;
}

/**
 * Enviar mensaje de texto via WhatsApp Cloud API
 */
function enviarMensajeTexto($phoneNumberId, $accessToken, $to, $message) {
    $url = GRAPH_API_URL . '/' . $phoneNumberId . '/messages';

    $payload = [
        'messaging_product' => 'whatsapp',
        'recipient_type' => 'individual',
        'to' => $to,
        'type' => 'text',
        'text' => [
            'preview_url' => true,
            'body' => $message
        ]
    ];

    return enviarRequestWhatsApp($url, $accessToken, $payload);
}

/**
 * Enviar imagen via WhatsApp Cloud API
 */
function enviarImagen($phoneNumberId, $accessToken, $to, $imageUrl, $caption = '') {
    $url = GRAPH_API_URL . '/' . $phoneNumberId . '/messages';

    $payload = [
        'messaging_product' => 'whatsapp',
        'recipient_type' => 'individual',
        'to' => $to,
        'type' => 'image',
        'image' => [
            'link' => $imageUrl
        ]
    ];

    if (!empty($caption)) {
        $payload['image']['caption'] = $caption;
    }

    return enviarRequestWhatsApp($url, $accessToken, $payload);
}

/**
 * Enviar documento via WhatsApp Cloud API
 */
function enviarDocumento($phoneNumberId, $accessToken, $to, $documentUrl, $filename, $caption = '') {
    $url = GRAPH_API_URL . '/' . $phoneNumberId . '/messages';

    $payload = [
        'messaging_product' => 'whatsapp',
        'recipient_type' => 'individual',
        'to' => $to,
        'type' => 'document',
        'document' => [
            'link' => $documentUrl,
            'filename' => $filename
        ]
    ];

    if (!empty($caption)) {
        $payload['document']['caption'] = $caption;
    }

    return enviarRequestWhatsApp($url, $accessToken, $payload);
}

/**
 * Enviar audio via WhatsApp Cloud API
 */
function enviarAudio($phoneNumberId, $accessToken, $to, $audioUrl) {
    $url = GRAPH_API_URL . '/' . $phoneNumberId . '/messages';

    $payload = [
        'messaging_product' => 'whatsapp',
        'recipient_type' => 'individual',
        'to' => $to,
        'type' => 'audio',
        'audio' => [
            'link' => $audioUrl
        ]
    ];

    return enviarRequestWhatsApp($url, $accessToken, $payload);
}

/**
 * Enviar video via WhatsApp Cloud API
 */
function enviarVideo($phoneNumberId, $accessToken, $to, $videoUrl, $caption = '') {
    $url = GRAPH_API_URL . '/' . $phoneNumberId . '/messages';

    $payload = [
        'messaging_product' => 'whatsapp',
        'recipient_type' => 'individual',
        'to' => $to,
        'type' => 'video',
        'video' => [
            'link' => $videoUrl
        ]
    ];

    if (!empty($caption)) {
        $payload['video']['caption'] = $caption;
    }

    return enviarRequestWhatsApp($url, $accessToken, $payload);
}

/**
 * Registrar mensaje de salida en la tabla Mensaje
 * @param string $telefono Número de teléfono formateado (wa_id)
 * @param int|string $idEmpresa ID de la empresa
 * @param string $contenido Contenido del mensaje
 * @param string $tipoMensaje Tipo de mensaje (text, image, document, audio, video)
 * @param string|null $widMensaje ID del mensaje en WhatsApp (de la respuesta de la API)
 * @param string|null $contenidoArchivo URL del archivo (imagen, documento, etc.)
 * @return array Resultado de la operación
 */
function registrarMensajeSalida($telefono, $idEmpresa, $contenido, $tipoMensaje = 'text', $widMensaje = null, $contenidoArchivo = null) {
    try {
        if (empty($idEmpresa)) {
            error_log("⚠️ No se registra mensaje en BD: id_empresa vacío");
            return ['success' => false, 'error' => 'id_empresa vacío'];
        }

        $conexion = new Conexion();
        $pdo = $conexion->conectar();

        if (!$pdo) {
            error_log("❌ No se pudo conectar a BD para registrar mensaje de salida");
            return ['success' => false, 'error' => 'No se pudo conectar a BD'];
        }

        // Buscar contacto por wa_id (teléfono) e id_empresa
        $sqlContacto = "SELECT id FROM Contacto
                        WHERE wa_id = :wa_id AND id_empresa = :id_empresa
                        AND estado_registro = 1";
        $stmtContacto = $pdo->prepare($sqlContacto);
        $stmtContacto->bindParam(':wa_id', $telefono);
        $stmtContacto->bindParam(':id_empresa', $idEmpresa, PDO::PARAM_INT);
        $stmtContacto->execute();
        $contacto = $stmtContacto->fetch(PDO::FETCH_ASSOC);

        if (!$contacto) {
            error_log("⚠️ No se encontró contacto con wa_id: $telefono para empresa: $idEmpresa. No se registra mensaje.");
            return ['success' => false, 'error' => "Contacto no encontrado (wa_id: $telefono, empresa: $idEmpresa)"];
        }

        $idContacto = $contacto['id'];
        $zonaLima = new DateTimeZone('America/Lima');
        $fechaHora = (new DateTime('now', $zonaLima))->format('Y-m-d H:i:s');

        $sqlMensaje = "INSERT INTO Mensaje (
                        id_contacto,
                        direccion,
                        tipo_mensaje,
                        wid_mensaje,
                        contenido,
                        contenido_archivo,
                        fecha_hora,
                        id_empresa,
                        es_recordatorio,
                        concluido,
                        fecha_registro,
                        estado_registro
                    ) VALUES (
                        :id_contacto,
                        'salida',
                        :tipo_mensaje,
                        :wid_mensaje,
                        :contenido,
                        :contenido_archivo,
                        :fecha_hora,
                        :id_empresa,
                        0,
                        0,
                        NOW(),
                        1
                    )";

        $stmtMensaje = $pdo->prepare($sqlMensaje);
        $stmtMensaje->bindParam(':id_contacto', $idContacto, PDO::PARAM_INT);
        $stmtMensaje->bindParam(':tipo_mensaje', $tipoMensaje);
        $stmtMensaje->bindParam(':wid_mensaje', $widMensaje);
        $stmtMensaje->bindParam(':contenido', $contenido);
        $stmtMensaje->bindParam(':contenido_archivo', $contenidoArchivo);
        $stmtMensaje->bindParam(':fecha_hora', $fechaHora);
        $stmtMensaje->bindParam(':id_empresa', $idEmpresa, PDO::PARAM_INT);
        $stmtMensaje->execute();

        $idMensaje = $pdo->lastInsertId();
        error_log("✅ Mensaje de salida registrado en BD - ID: $idMensaje, contacto: $idContacto, empresa: $idEmpresa, tipo: $tipoMensaje");

        return [
            'success' => true,
            'id_mensaje' => $idMensaje,
            'id_contacto' => $idContacto
        ];

    } catch (Exception $e) {
        error_log("❌ Error al registrar mensaje de salida en BD: " . $e->getMessage());
        return ['success' => false, 'error' => $e->getMessage()];
    }
}

/**
 * Ejecutar request a WhatsApp Cloud API
 */
function enviarRequestWhatsApp($url, $accessToken, $payload) {
    $ch = curl_init($url);

    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'Content-Type: application/json',
        'Authorization: Bearer ' . $accessToken
    ]);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true);

    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlError = curl_error($ch);
    // curl_close() no es necesario en PHP 8.0+ (el recurso se cierra automáticamente)

    return [
        'response' => $response,
        'http_code' => $httpCode,
        'curl_error' => $curlError
    ];
}

try {
    // Usar credenciales (ya sean de Maravia, BD o directas)
    $accessToken = $access_token;
    $phoneNumberId = $phone_number_id;

    // Determinar la fuente de las credenciales para el debug
    $credentialsFrom = 'direct';
    if (!empty($id_empresa) && isset($credenciales)) {
        $idPlataforma = $credenciales['id_plataforma'] ?? null;
        if (($idPlataforma == 1 || $idPlataforma == 5) && !empty(MARAVIA_ACCESS_TOKEN)) {
            $credentialsFrom = 'maravia_coexistence';
        } else {
            $credentialsFrom = 'database';
        }
    }

    // Formatear número de teléfono
    $formattedPhone = formatearNumeroTelefono($phone);

    // Log para debugging
    $sourceInfo = !empty($id_empresa) ? "empresa: $id_empresa (via: $credentialsFrom)" : "credenciales directas";
    error_log("Enviando mensaje tipo: $type a: $formattedPhone via WhatsApp Cloud API ($sourceInfo)");

    // Enviar mensaje según el tipo
    $result = null;

    switch ($type) {
        case 'text':
            $result = enviarMensajeTexto($phoneNumberId, $accessToken, $formattedPhone, $message);
            break;

        case 'image':
            $result = enviarImagen($phoneNumberId, $accessToken, $formattedPhone, $image_url, $message);
            break;

        case 'document':
            $result = enviarDocumento($phoneNumberId, $accessToken, $formattedPhone, $document_url, $filename, $message);
            break;

        case 'audio':
            $result = enviarAudio($phoneNumberId, $accessToken, $formattedPhone, $audio_url);
            break;

        case 'video':
            $result = enviarVideo($phoneNumberId, $accessToken, $formattedPhone, $video_url, $message);
            break;
    }

    // Manejar errores de cURL
    if (!empty($result['curl_error'])) {
        http_response_code(500);
        echo json_encode([
            'success' => false,
            'error' => 'Error de conexión con WhatsApp Cloud API',
            'details' => $result['curl_error'],
            'type' => $type
        ]);
        exit;
    }

    // Decodificar respuesta
    $responseData = json_decode($result['response'], true);
    $httpCode = $result['http_code'];

    // Verificar código de respuesta HTTP
    if ($httpCode >= 200 && $httpCode < 300) {
        // Extraer wid_mensaje de la respuesta de WhatsApp API
        $widMensaje = $responseData['messages'][0]['id'] ?? null;

        // Determinar contenido del archivo según tipo
        $contenidoArchivo = null;
        switch ($type) {
            case 'image': $contenidoArchivo = $image_url; break;
            case 'document': $contenidoArchivo = $document_url; break;
            case 'audio': $contenidoArchivo = $audio_url; break;
            case 'video': $contenidoArchivo = $video_url; break;
        }

        // Registrar mensaje de salida en BD
        $registroBD = registrarMensajeSalida(
            $formattedPhone,
            $id_empresa,
            $message,
            $type,
            $widMensaje,
            $contenidoArchivo
        );

        // Respuesta exitosa
        http_response_code(200);
        echo json_encode([
            'success' => true,
            'message' => 'Mensaje enviado correctamente',
            'response' => $responseData,
            'http_code' => $httpCode,
            'registro_bd' => $registroBD,
            'debug' => [
                'type' => $type,
                'to' => $formattedPhone,
                'phone_number_id' => $phoneNumberId,
                'id_empresa' => $id_empresa ?: null,
                'source' => 'whatsapp_cloud_api',
                'credentials_from' => $credentialsFrom
            ]
        ]);
    } else {
        // Error del servidor de WhatsApp
        http_response_code($httpCode);
        echo json_encode([
            'success' => false,
            'error' => 'Error al enviar mensaje',
            'details' => $responseData,
            'http_code' => $httpCode,
            'debug' => [
                'type' => $type,
                'to' => $formattedPhone,
                'id_empresa' => $id_empresa ?: null,
                'source' => 'whatsapp_cloud_api',
                'credentials_from' => $credentialsFrom
            ]
        ]);
    }

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error' => 'Error en el servidor',
        'details' => $e->getMessage(),
        'trace' => $e->getTraceAsString()
    ]);
}
?>
