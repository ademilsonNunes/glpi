from __future__ import annotations
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from cachetools import TTLCache
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import get_current_user, login_handler
from .config import settings
from .db import close_tunnel, db_probe, ensure_tunnel, tunnel_status
from .metrics import compute_itil_metrics, compute_open_sla_monitor, compute_management_pack, compute_technician_kpis
from .sql_loader import KPI_TO_FILE, execute_sql_file

app = FastAPI(title="GLPI ITIL KPIs API", version="0.1.0")
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("glpi.api")
cache = TTLCache(maxsize=settings.cache_maxsize, ttl=settings.cache_ttl_seconds)

app.add_api_route("/auth/login", login_handler, methods=["POST"])
app.mount("/app", StaticFiles(directory="web", html=True), name="webapp")


@app.on_event("startup")
def _startup():
    ensure_tunnel()


@app.on_event("shutdown")
def _shutdown():
    close_tunnel()


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    started = time.perf_counter()
    req_id = str(uuid.uuid4())[:8]
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - started) * 1000
        logger.exception(
            "request_error req_id=%s method=%s path=%s duration_ms=%.1f",
            req_id,
            request.method,
            request.url.path,
            elapsed,
        )
        raise
    elapsed = (time.perf_counter() - started) * 1000
    logger.info(
        "request req_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        req_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    response.headers["X-Request-Id"] = req_id
    return response


@app.get("/health")
def health(details: int = Query(1, ge=0, le=1)):
    if details == 0:
        return {"status": "ok"}
    tun = tunnel_status()
    db = db_probe()
    overall_ok = bool(db.get("ok"))
    return {
        "status": "ok" if overall_ok else "degraded",
        "api": {"ok": True, "version": app.version},
        "tunnel": tun,
        "db": db,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _cached(key: str, loader):
    if key in cache:
        return cache[key]
    data = loader()
    cache[key] = data
    return data


def _run_named_query(name: str):
    filename = KPI_TO_FILE.get(name)
    if not filename:
        raise HTTPException(status_code=404, detail="Query not found")
    try:
        return execute_sql_file(filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


def _query_filters(
    since: Optional[str] = Query(None, description="YYYY-MM-DD"),
    until: Optional[str] = Query(None, description="YYYY-MM-DD"),
    tech: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
):
    return {
        "since": since,
        "until": until,
        "tech": tech or "",
        "category": category or "",
        "priority": priority or "",
    }


def _parse_row_date(row: dict) -> datetime | None:
    for key in ("data_abertura", "data_followup", "abertura_chamado", "data_inicio", "inicio", "date"):
        if row.get(key) is None:
            continue
        val = row.get(key)
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val))
        except Exception:
            return None
    return None


def _contains_any(row: dict, keys: tuple[str, ...], term: str) -> bool:
    if not term:
        return True
    values = [row.get(k) for k in keys if row.get(k) is not None]
    if not values:
        return True
    term_l = term.lower()
    return any(term_l in str(v).lower() for v in values)


def _apply_filters(rows: list[dict], filters: dict) -> list[dict]:
    if not rows:
        return rows
    since = filters.get("since")
    until = filters.get("until")
    tech = (filters.get("tech") or "").strip()
    category = (filters.get("category") or "").strip()
    priority = (filters.get("priority") or "").strip()
    if not any([since, until, tech, category, priority]):
        return rows

    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None
    if since_dt and since_dt.tzinfo is None:
        since_dt = since_dt.replace(tzinfo=timezone.utc)
    if until_dt and until_dt.tzinfo is None:
        until_dt = until_dt.replace(tzinfo=timezone.utc)

    out: list[dict] = []
    for row in rows:
        d = _parse_row_date(row)
        if d and d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        if since_dt and d and d < since_dt:
            continue
        if until_dt and d and d > until_dt:
            continue
        if not _contains_any(row, ("tecnico", "autor", "usuario"), tech):
            continue
        if not _contains_any(row, ("categoria", "categoria_nivel1", "top_categoria"), category):
            continue
        if not _contains_any(row, ("prioridade", "prioridade_label", "prioridade_selecionada"), priority):
            continue
        out.append(row)
    return out


def _kpi(name: str, filters: dict):
    data = _cached(f"kpi:{name}", lambda: _run_named_query(name))
    return JSONResponse(jsonable_encoder(_apply_filters(data, filters)))


@app.get("/kpis/base")
def kpi_base(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("base", filters)


@app.get("/metrics/itil-summary")
def metrics_itil_summary(
    since: Optional[str] = Query(None, description="YYYY-MM-DD"),
    until: Optional[str] = Query(None, description="YYYY-MM-DD"),
    _: str = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    until_dt = datetime.fromisoformat(until).replace(tzinfo=timezone.utc) if until else now
    since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else (until_dt - timedelta(days=30))
    try:
        data = compute_itil_metrics(since_dt, until_dt)
        return JSONResponse(jsonable_encoder(data))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


@app.get("/metrics/open-sla-monitor")
def metrics_open_sla_monitor(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    try:
        data = compute_open_sla_monitor(
            since=filters.get("since"),
            until=filters.get("until"),
            tech=filters.get("tech"),
            category=filters.get("category"),
            priority=filters.get("priority"),
        )
        return JSONResponse(jsonable_encoder(data))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


@app.get("/metrics/management-pack")
def metrics_management_pack(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    try:
        data = compute_management_pack(
            since=filters.get("since"),
            until=filters.get("until"),
            tech=filters.get("tech"),
            category=filters.get("category"),
            priority=filters.get("priority"),
        )
        return JSONResponse(jsonable_encoder(data))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


@app.get("/metrics/tecnicos-kpis")
def metrics_tecnicos_kpis(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    try:
        data = compute_technician_kpis(
            since=filters.get("since"),
            until=filters.get("until"),
            tech=filters.get("tech"),
            category=filters.get("category"),
            priority=filters.get("priority"),
        )
        return JSONResponse(jsonable_encoder(data))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


@app.get("/kpis/reincidencia")
def kpi_reincidencia(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("reincidencia", filters)


@app.get("/kpis/followups")
def kpi_followups(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("followups", filters)


@app.get("/kpis/qualidade-abertura")
def kpi_qualidade_abertura(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("qualidade_abertura", filters)


@app.get("/kpis/score-departamento")
def kpi_score_departamento(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("score_departamento", filters)


@app.get("/kpis/first-response-time")
def kpi_frt(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("first_response_time", filters)


@app.get("/kpis/interacoes")
def kpi_interacoes(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("interacoes", filters)


@app.get("/kpis/problemas-itil")
def kpi_problemas_itil(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("problemas_itil", filters)


@app.get("/kpis/recorrentes-impacto")
def kpi_recorrentes_impacto(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("recorrentes_impacto", filters)


@app.get("/kpis/ranking-usuarios-treinamento")
def kpi_ranking_usuarios_treinamento(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("ranking_usuarios_treinamento", filters)


@app.get("/kpis/heatmap")
def kpi_heatmap(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("heatmap", filters)


@app.get("/kpis/dashboard-semanal")
def kpi_dashboard_semanal(filters: dict = Depends(_query_filters), _: str = Depends(get_current_user)):
    return _kpi("dashboard_semanal", filters)


@app.get("/", response_class=HTMLResponse)
def root():
    items = [
        ("Base", "/kpis/base"),
        ("Reincidencia", "/kpis/reincidencia"),
        ("Followups", "/kpis/followups"),
        ("Qualidade de Abertura", "/kpis/qualidade-abertura"),
        ("Score por Departamento", "/kpis/score-departamento"),
        ("First Response Time", "/kpis/first-response-time"),
        ("Interacoes por Chamado", "/kpis/interacoes"),
        ("Problemas ITIL", "/kpis/problemas-itil"),
        ("Recorrentes Impacto", "/kpis/recorrentes-impacto"),
        ("Ranking Usuarios Treinamento", "/kpis/ranking-usuarios-treinamento"),
        ("Heatmap Dia/Hora", "/kpis/heatmap"),
        ("Dashboard Semanal", "/kpis/dashboard-semanal"),
    ]
    links = "".join(f'<li><a href="{href}">{label}</a></li>' for label, href in items)
    return f"<h1>GLPI ITIL KPIs API</h1><ul>{links}</ul>"
