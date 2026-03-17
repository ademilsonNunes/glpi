from __future__ import annotations
import mysql.connector
from mysql.connector import pooling
from typing import Any, Dict, List
from .config import settings
import os
from sshtunnel import SSHTunnelForwarder
import logging

_pool: pooling.MySQLConnectionPool | None = None
_tunnel: SSHTunnelForwarder | None = None
_local_tunnel_port: int | None = None
logger = logging.getLogger(__name__)


def ensure_tunnel() -> None:
    global _tunnel, _local_tunnel_port
    if _tunnel is not None:
        return
    if settings.ssh_host and settings.ssh_user:
        try:
            _tunnel = SSHTunnelForwarder(
                (settings.ssh_host, settings.ssh_port),
                ssh_username=settings.ssh_user,
                ssh_password=settings.ssh_password or None,
                remote_bind_address=(settings.db_host, settings.db_port),
                local_bind_address=("127.0.0.1", 0),
            )
            _tunnel.start()
            _local_tunnel_port = int(_tunnel.local_bind_port)
        except Exception:
            _tunnel = None
            _local_tunnel_port = None
            logger.exception("Failed to start SSH tunnel")
            if settings.ssh_strict:
                raise
    else:
        _tunnel = None
        _local_tunnel_port = None


def close_tunnel() -> None:
    global _tunnel, _local_tunnel_port
    try:
        if _tunnel is not None:
            _tunnel.stop()
    finally:
        _tunnel = None
        _local_tunnel_port = None


def tunnel_status() -> Dict[str, Any]:
    return {
        "enabled": bool(settings.ssh_host and settings.ssh_user),
        "active": _tunnel is not None and _local_tunnel_port is not None,
        "local_port": _local_tunnel_port,
    }


def get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is not None:
        return _pool

    # Try twice to reduce transient failures when SSH tunnel or DB is unstable.
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            ensure_tunnel()
            host = settings.db_host
            port = settings.db_port
            if _local_tunnel_port is not None:
                host = "127.0.0.1"
                port = _local_tunnel_port
            elif settings.ssh_host and settings.ssh_user:
                logger.warning(
                    "SSH configured but tunnel unavailable. Falling back to direct DB connection %s:%s",
                    host,
                    port,
                )

            _pool = pooling.MySQLConnectionPool(
                pool_name="glpi_pool",
                pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
                pool_reset_session=True,
                host=host,
                port=port,
                database=settings.db_name,
                user=settings.db_user,
                password=settings.db_password,
                autocommit=False,
                use_pure=True,
                allow_local_infile=False,
                get_warnings=False,
                auth_plugin="mysql_native_password",
                connection_timeout=settings.db_connect_timeout,
                consume_results=True,
            )
            return _pool
        except Exception as e:
            last_error = e
            _pool = None
            close_tunnel()
            if attempt == 0:
                continue
            raise

    if last_error:
        raise last_error
    return _pool


def reset_pool() -> None:
    global _pool
    _pool = None


def db_probe() -> Dict[str, Any]:
    try:
        rows = execute_sql("SELECT 1 AS ok", multi=False)
        ok = bool(rows and rows[0].get("ok") == 1)
        target = "tunnel" if _local_tunnel_port is not None else "direct"
        return {"ok": ok, "target": target}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def execute_sql(sql: str, params: Dict[str, Any] | None = None, multi: bool = False) -> List[Dict[str, Any]]:
    pool = get_pool()
    conn = pool.get_connection()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True, buffered=True)
        if multi:
            result_rows: List[Dict[str, Any]] = []
            for result in cursor.execute(sql, params or {}, multi=True):
                if result.with_rows:
                    result_rows = result.fetchall()
            return result_rows
        else:
            cursor.execute(sql, params or {})
            if cursor.with_rows:
                return cursor.fetchall()
            return []
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
