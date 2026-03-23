<?php
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With');

require_once __DIR__ . '/../conexion.php';

// Manejar preflight OPTIONS
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

// Validar método
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Método no permitido. Use POST']);
    exit;
}

// Obtener JSON del body
$data = json_decode(file_get_contents('php://input'), true);

if (!$data) {
    http_response_code(400);
    echo json_encode(['error' => 'JSON inválido o vacío']);
    exit;
}

$codOpe = $data['codOpe'] ?? null;
$id_empresa = $data['id_empresa'] ?? null;

if (!$codOpe) {
    http_response_code(400);
    echo json_encode(['error' => 'El campo codOpe es obligatorio']);
    exit;
}

if (!$id_empresa) {
    http_response_code(400);
    echo json_encode(['error' => 'El campo id_empresa es obligatorio']);
    exit;
}

// ================= FUNCIONES =======================

/**
 * Buscar proveedor por término (nombres, apellidos, razón social, RUC, documento)
 */
function buscarProveedor($pdo, $empresa_id, $termino) {
    try {
        if (empty($termino)) {
            echo json_encode([
                'success' => false,
                'found' => false,
                'message' => 'Término de búsqueda requerido'
            ]);
            return;
        }

        $sql = "SELECT
                    pr.id as proveedor_id,
                    p.id as persona_id,
                    p.tipo_persona,
                    p.nombres,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.razon_social,
                    p.nombre_comercial,
                    p.numero_documento,
                    p.ruc,
                    p.telefono,
                    p.correo,
                    p.direccion,
                    pr.id_categoria_proveedor,
                    cp.nombre_categoria as categoria_proveedor_nombre
                FROM Proveedor pr
                INNER JOIN Persona p ON pr.id_persona = p.id
                LEFT JOIN CategoriaProveedor cp ON pr.id_categoria_proveedor = cp.id
                WHERE pr.id_empresa = :empresa_id
                AND p.id_empresa = :empresa_id
                AND pr.estado_registro = 1
                AND p.estado_registro = 1
                AND (
                    CONCAT(COALESCE(p.nombres,''), ' ', COALESCE(p.apellido_paterno,''), ' ', COALESCE(p.apellido_materno,'')) LIKE :termino
                    OR COALESCE(p.razon_social,'') LIKE :termino
                    OR COALESCE(p.nombre_comercial,'') LIKE :termino
                    OR COALESCE(p.numero_documento,'') LIKE :termino
                    OR COALESCE(p.ruc,'') LIKE :termino
                )
                LIMIT 1";

        $stmt = $pdo->prepare($sql);
        $terminoBusqueda = '%' . $termino . '%';
        $stmt->bindParam(':empresa_id', $empresa_id, PDO::PARAM_INT);
        $stmt->bindParam(':termino', $terminoBusqueda, PDO::PARAM_STR);
        $stmt->execute();

        $proveedor = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($proveedor) {
            echo json_encode([
                'success' => true,
                'found' => true,
                'proveedor_id' => $proveedor['proveedor_id'],
                'persona_id' => $proveedor['persona_id'],
                'data' => $proveedor
            ]);
        } else {
            echo json_encode([
                'success' => true,
                'found' => false,
                'proveedor_id' => false,
                'message' => 'Proveedor no encontrado'
            ]);
        }
    } catch (PDOException $e) {
        http_response_code(500);
        echo json_encode([
            'success' => false,
            'error' => 'Error en la búsqueda',
            'details' => $e->getMessage()
        ]);
    }
}

/**
 * Registrar proveedor persona natural
 */
function registrarProveedor($pdo, $data, $empresa_id) {
    // Log de entrada para debug
    error_log("📝 REGISTRAR_PROVEEDOR_SIMPLE - Datos recibidos: " . json_encode($data, JSON_UNESCAPED_UNICODE));

    // Validar campos obligatorios
    $tipo_persona = $data['tipo_persona'] ?? 1; // 1=Natural, 2=Jurídica
    error_log("👤 Tipo persona: $tipo_persona (1=Natural, 2=Jurídica)");

    if ($tipo_persona == 1) {
        // Persona Natural
        $campos_requeridos = ['nombres', 'apellido_paterno', 'id_tipo_documento', 'numero_documento'];

        foreach ($campos_requeridos as $campo) {
            if (empty($data[$campo])) {
                http_response_code(400);
                echo json_encode(['error' => "Campo requerido para Persona Natural: $campo"]);
                return;
            }
        }
    } else {
        // Persona Jurídica
        // Requiere id_tipo_documento Y (razon_social O nombres+apellidos) Y (ruc O numero_documento)
        if (empty($data['id_tipo_documento'])) {
            http_response_code(400);
            echo json_encode(['error' => 'Campo requerido: id_tipo_documento']);
            return;
        }

        if (empty($data['razon_social']) && empty($data['nombres'])) {
            http_response_code(400);
            echo json_encode(['error' => 'Para Persona Jurídica se requiere razon_social o nombres+apellidos']);
            return;
        }

        if (empty($data['ruc']) && empty($data['numero_documento'])) {
            http_response_code(400);
            echo json_encode(['error' => 'Para Persona Jurídica se requiere ruc o numero_documento']);
            return;
        }
    }

    try {
        $pdo->beginTransaction();

        // 1. Insertar Persona
        if ($tipo_persona == 1) {
            // Persona Natural
            $sqlPersona = "INSERT INTO Persona (
                nombres, apellido_paterno, apellido_materno, id_tipo_documento,
                numero_documento, telefono, correo, direccion,
                fecha_nacimiento, genero, tipo_persona, id_empresa,
                estado_registro
            ) VALUES (
                :nombres, :apellido_paterno, :apellido_materno, :id_tipo_documento,
                :numero_documento, :telefono, :correo, :direccion,
                :fecha_nacimiento, :genero, :tipo_persona, :id_empresa,
                1
            )";

            $stmtPersona = $pdo->prepare($sqlPersona);
            $stmtPersona->bindParam(':nombres', $data['nombres']);
            $stmtPersona->bindParam(':apellido_paterno', $data['apellido_paterno']);
            $apellido_materno = $data['apellido_materno'] ?? '';
            $stmtPersona->bindParam(':apellido_materno', $apellido_materno);
            $stmtPersona->bindParam(':id_tipo_documento', $data['id_tipo_documento'], PDO::PARAM_INT);
            $stmtPersona->bindParam(':numero_documento', $data['numero_documento']);

            $telefono = $data['telefono'] ?? null;
            $correo = $data['correo'] ?? null;
            $direccion = $data['direccion'] ?? null;
            $fecha_nacimiento = $data['fecha_nacimiento'] ?? null;
            $genero = $data['genero'] ?? null;

            $stmtPersona->bindParam(':telefono', $telefono);
            $stmtPersona->bindParam(':correo', $correo);
            $stmtPersona->bindParam(':direccion', $direccion);
            $stmtPersona->bindParam(':fecha_nacimiento', $fecha_nacimiento);
            $stmtPersona->bindParam(':genero', $genero);
            $stmtPersona->bindParam(':tipo_persona', $tipo_persona, PDO::PARAM_INT);
            $stmtPersona->bindParam(':id_empresa', $empresa_id, PDO::PARAM_INT);
        } else {
            // Persona Jurídica
            // Si no viene razon_social pero vienen nombres/apellidos, construirla automáticamente
            if (empty($data['razon_social']) && !empty($data['nombres'])) {
                $razon_social = trim(
                    ($data['nombres'] ?? '') . ' ' .
                    ($data['apellido_paterno'] ?? '') . ' ' .
                    ($data['apellido_materno'] ?? '')
                );
                error_log("🔄 Auto-construyendo razón social: $razon_social");
            } else {
                $razon_social = $data['razon_social'] ?? '';
            }

            // Manejar RUC: puede venir como 'ruc' o 'numero_documento'
            $ruc = $data['ruc'] ?? $data['numero_documento'] ?? '';

            if (empty($razon_social)) {
                http_response_code(400);
                echo json_encode(['error' => 'Para Persona Jurídica se requiere razon_social o nombres+apellidos']);
                $pdo->rollBack();
                return;
            }

            if (empty($ruc)) {
                http_response_code(400);
                echo json_encode(['error' => 'Para Persona Jurídica se requiere ruc o numero_documento']);
                $pdo->rollBack();
                return;
            }

            $sqlPersona = "INSERT INTO Persona (
                razon_social, nombre_comercial, id_tipo_documento, ruc,
                telefono, correo, direccion, representante_legal,
                tipo_persona, id_empresa, nombres, apellido_paterno, apellido_materno,
                numero_documento, estado_registro
            ) VALUES (
                :razon_social, :nombre_comercial, :id_tipo_documento, :ruc,
                :telefono, :correo, :direccion, :representante_legal,
                :tipo_persona, :id_empresa, '', '', '',
                :ruc, 1
            )";

            $stmtPersona = $pdo->prepare($sqlPersona);
            $stmtPersona->bindParam(':razon_social', $razon_social);

            $nombre_comercial = $data['nombre_comercial'] ?? $data['nombres'] ?? $razon_social;
            $stmtPersona->bindParam(':nombre_comercial', $nombre_comercial);
            $stmtPersona->bindParam(':id_tipo_documento', $data['id_tipo_documento'], PDO::PARAM_INT);
            $stmtPersona->bindParam(':ruc', $ruc);

            $telefono = $data['telefono'] ?? null;
            $correo = $data['correo'] ?? null;
            $direccion = $data['direccion'] ?? null;
            $representante_legal = $data['representante_legal'] ?? null;

            $stmtPersona->bindParam(':telefono', $telefono);
            $stmtPersona->bindParam(':correo', $correo);
            $stmtPersona->bindParam(':direccion', $direccion);
            $stmtPersona->bindParam(':representante_legal', $representante_legal);
            $stmtPersona->bindParam(':tipo_persona', $tipo_persona, PDO::PARAM_INT);
            $stmtPersona->bindParam(':id_empresa', $empresa_id, PDO::PARAM_INT);
        }

        $stmtPersona->execute();
        $persona_id = $pdo->lastInsertId();

        // 2. Insertar Proveedor
        $sqlProveedor = "INSERT INTO Proveedor (
            id_persona, id_empresa, id_categoria_proveedor, estado_registro
        ) VALUES (
            :id_persona, :id_empresa, :id_categoria_proveedor, 1
        )";

        $stmtProveedor = $pdo->prepare($sqlProveedor);
        $stmtProveedor->bindParam(':id_persona', $persona_id, PDO::PARAM_INT);
        $stmtProveedor->bindParam(':id_empresa', $empresa_id, PDO::PARAM_INT);

        // id_categoria_proveedor es opcional
        $id_categoria_proveedor = !empty($data['id_categoria_proveedor']) ? $data['id_categoria_proveedor'] : null;
        $stmtProveedor->bindParam(':id_categoria_proveedor', $id_categoria_proveedor, $id_categoria_proveedor === null ? PDO::PARAM_NULL : PDO::PARAM_INT);

        $stmtProveedor->execute();

        $proveedor_id = $pdo->lastInsertId();

        $pdo->commit();

        echo json_encode([
            'success' => true,
            'message' => 'Proveedor registrado exitosamente',
            'proveedor_id' => $proveedor_id,
            'persona_id' => $persona_id
        ]);

    } catch (Exception $e) {
        $pdo->rollBack();
        http_response_code(500);
        echo json_encode([
            'error' => 'Error al registrar proveedor',
            'details' => $e->getMessage()
        ]);
    }
}

// =====================================================

try {
    $conexion = new Conexion();
    $pdo = $conexion->conectar();

    switch ($codOpe) {

        case "BUSCAR_PROVEEDOR":
            $termino = trim($data['nombre_completo'] ?? '');
            buscarProveedor($pdo, $id_empresa, $termino);
            break;

        case "REGISTRAR_PROVEEDOR_SIMPLE":
            registrarProveedor($pdo, $data, $id_empresa);
            break;

        default:
            http_response_code(400);
            echo json_encode(['error' => 'Operación no reconocida']);
            break;
    }

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        'error' => 'Error en el servidor',
        'details' => $e->getMessage()
    ]);
}
