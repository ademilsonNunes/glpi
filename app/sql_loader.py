from __future__ import annotations
import os
from typing import Dict, Any, List
from .config import settings
from .db import execute_sql


def _abs_sql_path(filename: str) -> str:
    base = settings.sql_dir
    path = os.path.join(base, filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"SQL file not found: {path}")
    return path


def _read_sql(filename: str) -> str:
    with open(_abs_sql_path(filename), "r", encoding="utf-8") as f:
        return f.read()


def _split_sql_statements(sql: str) -> List[str]:
    statements: List[str] = []
    chunk: List[str] = []
    for raw_line in sql.splitlines():
        line = raw_line
        if "--" in line:
            line = line.split("--", 1)[0]
        line = line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        chunk.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(chunk).strip().rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            chunk = []
    if chunk:
        stmt = "\n".join(chunk).strip().rstrip(";").strip()
        if stmt:
            statements.append(stmt)
    return statements


def execute_sql_file(filename: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """
    Executes a .sql file and returns rows from the last statement that returns results.
    Supports multi-statement files (e.g., SET ...; SELECT ...).
    """
    sql = _read_sql(filename)
    # Simple, safe parameter replacement for {{param}} placeholders if present
    if params:
        for key, val in params.items():
            placeholder = "{{" + key + "}}"
            if placeholder in sql:
                if isinstance(val, str):
                    val_str = val.replace("'", "''")
                    sql = sql.replace(placeholder, f"'{val_str}'")
                else:
                    sql = sql.replace(placeholder, str(val))
    statements = _split_sql_statements(sql)
    if not statements:
        return []

    last_rows: List[Dict[str, Any]] = []
    for stmt in statements:
        rows = execute_sql(stmt, multi=False)
        if rows:
            last_rows = rows
    return last_rows


# Convenience wrappers mapping files to friendly names
KPI_TO_FILE = {
    "base": "q01_chamados_base.sql",
    "reincidencia": "q02_reincidencia.sql",
    "followups": "q03_followups_mensagens.sql",
    "qualidade_abertura": "q04_qualidade_abertura.sql",
    "score_departamento": "q05_score_departamento.sql",
    "first_response_time": "q06_first_response_time.sql",
    "interacoes": "q07_interacoes_por_chamado.sql",
    "problemas_itil": "q08_problemas_itil.sql",
    "recorrentes_impacto": "q09_recorrentes_impacto.sql",
    "ranking_usuarios_treinamento": "q10_ranking_usuarios_treinamento.sql",
    "heatmap": "q11_heatmap_dia_hora.sql",
    "dashboard_semanal": "q12_dashboard_semanal.sql",
}
