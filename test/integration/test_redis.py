"""
Tests de conexión y manejo de Redis (RedisCacheRepository).

No depende de .env: la URL se define abajo en REDIS_URL_TEST.
"""
from __future__ import annotations

import os
import sys

# Raíz del proyecto (carpeta que contiene test/)
_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _raiz)

# URL de Redis para los tests (este archivo no usa .env)
REDIS_URL_TEST = "redis://127.0.0.1:6379/0"

# Claves de prueba para no contaminar datos reales
WA_ID_TEST = "test_redis_wa_001"
ID_EMPRESA_TEST = 99999


def get_redis_url() -> str:
    return REDIS_URL_TEST


def check_redis_available() -> bool:
    """Comprueba si Redis está alcanzable."""
    try:
        from redis import Redis
        r = Redis.from_url(get_redis_url(), decode_responses=False)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


def test_conexion():
    """Test 1: Conexión a Redis."""
    print("Test 1: Conexión a Redis...")
    url = get_redis_url()
    # Ocultar contraseña en salida
    url_safe = url.split("@")[-1] if "@" in url else url
    print(f"  REDIS_URL = ...@{url_safe}")
    if check_redis_available():
        print("  ✅ Conexión OK")
        return True
    print("  ❌ No se pudo conectar. Comprueba que Redis esté en marcha y REDIS_URL_TEST en este archivo.")
    return False


def test_repositorio_crud():
    """Test 2: RedisCacheRepository — insertar, consultar, actualizar, eliminar."""
    from redis import Redis
    from repositories.redis_cache_repository import RedisCacheRepository

    print("Test 2: RedisCacheRepository (CRUD)...")
    url = get_redis_url()
    try:
        client = Redis.from_url(url, decode_responses=False)
        repo = RedisCacheRepository(client, ttl=300)
    except Exception as e:
        print(f"  ❌ Error creando cliente: {e}")
        return False

    try:
        # Limpiar por si quedó de un test anterior
        repo.eliminar(WA_ID_TEST, ID_EMPRESA_TEST)

        # Insertar
        datos_in = {
            "cod_ope": "ventas",
            "entidad_nombre": "Test Cliente SA",
            "monto_total": 1500.50,
            "id_moneda": 1,
            "productos_json": [{"nombre": "Item Test", "cantidad": 2, "precio": 750.25}],
        }
        res_insert = repo.insertar(WA_ID_TEST, ID_EMPRESA_TEST, datos_in)
        assert res_insert.get("success") is True, "insertar debería devolver success True"
        print("  ✅ insertar OK")

        # Consultar
        reg = repo.consultar(WA_ID_TEST, ID_EMPRESA_TEST)
        assert reg is not None, "consultar debería devolver registro"
        assert reg.get("cod_ope") == "ventas"
        assert reg.get("entidad_nombre") == "Test Cliente SA"
        assert float(reg.get("monto_total", 0)) == 1500.50
        assert reg.get("id_moneda") == 1
        prods = reg.get("productos_json")
        assert isinstance(prods, list) and len(prods) == 1
        assert prods[0].get("nombre") == "Item Test"
        print("  ✅ consultar OK (con deserialización de JSON y números)")

        # Consultar lista
        lista = repo.consultar_lista(WA_ID_TEST, ID_EMPRESA_TEST)
        assert isinstance(lista, list) and len(lista) == 1
        assert lista[0].get("cod_ope") == "ventas"
        print("  ✅ consultar_lista OK")

        # Actualizar
        datos_up = {"monto_total": 2000.0, "ultima_pregunta": "¿Confirmo?"}
        res_up = repo.actualizar(WA_ID_TEST, ID_EMPRESA_TEST, datos_up)
        assert res_up.get("success") is True
        reg2 = repo.consultar(WA_ID_TEST, ID_EMPRESA_TEST)
        assert float(reg2.get("monto_total", 0)) == 2000.0
        assert reg2.get("ultima_pregunta") == "¿Confirmo?"
        assert reg2.get("entidad_nombre") == "Test Cliente SA"  # se mantiene
        print("  ✅ actualizar OK (merge con datos existentes)")

        # Eliminar
        res_del = repo.eliminar(WA_ID_TEST, ID_EMPRESA_TEST)
        assert res_del.get("success") is True
        assert repo.consultar(WA_ID_TEST, ID_EMPRESA_TEST) is None
        print("  ✅ eliminar OK")

        return True
    except AssertionError as e:
        print(f"  ❌ Assert fallido: {e}")
        repo.eliminar(WA_ID_TEST, ID_EMPRESA_TEST)
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        repo.eliminar(WA_ID_TEST, ID_EMPRESA_TEST)
        return False


def test_repositorio_sin_registro():
    """Test 3: consultar/consultar_lista cuando no existe la clave."""
    from redis import Redis
    from repositories.redis_cache_repository import RedisCacheRepository

    print("Test 3: Consultar clave inexistente...")
    url = get_redis_url()
    try:
        client = Redis.from_url(url, decode_responses=False)
        repo = RedisCacheRepository(client, ttl=300)
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

    wa_fantasma = "wa_inexistente_123"
    id_fantasma = 88888
    assert repo.consultar(wa_fantasma, id_fantasma) is None
    assert repo.consultar_lista(wa_fantasma, id_fantasma) == []
    print("  ✅ consultar devuelve None y consultar_lista []")
    return True


def test_eliminar_clave_inexistente():
    """Test 4: eliminar sobre clave que no existe devuelve success True (no falla)."""
    from redis import Redis
    from repositories.redis_cache_repository import RedisCacheRepository

    print("Test 4: eliminar clave inexistente (no debe lanzar)...")
    url = get_redis_url()
    try:
        client = Redis.from_url(url, decode_responses=False)
        repo = RedisCacheRepository(client, ttl=300)
        res = repo.eliminar("wa_no_existe_xyz", 77777)
        assert res.get("success") is True
        print("  ✅ eliminar devuelve success True (idempotente)")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False
    return True


def run_all():
    print("=" * 60)
    print("Tests de Redis (RedisCacheRepository)")
    print("=" * 60)
    if not check_redis_available():
        print("\n⚠️  Redis no disponible. No se ejecutan tests de integración.")
        print("   Edita REDIS_URL_TEST en este archivo con la URL de tu Redis.")
        return
    print()
    ok = 0
    for name, fn in [
        ("Conexión", test_conexion),
        ("CRUD", test_repositorio_crud),
        ("Clave inexistente", test_repositorio_sin_registro),
        ("Eliminar clave inexistente", test_eliminar_clave_inexistente),
    ]:
        if fn():
            ok += 1
        print()
    print("=" * 60)
    print(f"Resultado: {ok}/4 tests OK")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
