from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from collections import defaultdict
from statistics import median
from .db import execute_sql
from .business_time import business_minutes_between

PRIORITY_LABEL = {
    1: "Muito Baixa",
    2: "Baixa",
    3: "Média",
    4: "Alta",
    5: "Muito Alta",
    6: "Muito Alta",
}

SLA_HOURS_BY_PRIORITY = {
    "Muito Baixa": 120,
    "Baixa": 72,
    "Média": 24,
    "Alta": 8,
    "Muito Alta": 4,
}


def _parse_dt(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v))


def load_tickets_period(since: datetime, until: datetime) -> List[Dict[str, Any]]:
    rows = execute_sql(
        """
        SELECT
          t.id              AS ticket_id,
          t.priority        AS prioridade_num,
          t.date            AS data_abertura,
          COALESCE(t.solvedate, t.closedate) AS data_fechamento,
          t.status          AS status
        FROM glpi_tickets t
        WHERE t.is_deleted = 0
          AND t.date >= %(since)s
          AND t.date <= %(until)s
        """,
        {"since": since, "until": until},
    )
    resolved = [r for r in rows if r["data_fechamento"] is not None and r["status"] in (5, 6)]
    return resolved


def count_opened_and_backlog(since: datetime, until: datetime) -> Dict[str, int]:
    opened = execute_sql(
        """
        SELECT COUNT(*) AS total FROM glpi_tickets
        WHERE is_deleted = 0 AND date BETWEEN %(since)s AND %(until)s
        """,
        {"since": since, "until": until},
    )[0]["total"]
    backlog = execute_sql(
        """
        SELECT COUNT(*) AS total FROM glpi_tickets
        WHERE is_deleted = 0 AND status NOT IN (5,6) AND date <= %(until)s
        """,
        {"until": until},
    )[0]["total"]
    resolved = execute_sql(
        """
        SELECT COUNT(*) AS total FROM glpi_tickets
        WHERE is_deleted = 0
          AND COALESCE(solvedate, closedate) BETWEEN %(since)s AND %(until)s
          AND status IN (5,6)
        """,
        {"since": since, "until": until},
    )[0]["total"]
    return {"abertos_periodo": opened, "resolvidos_periodo": resolved, "backlog": backlog}


def compute_itil_metrics(since: datetime, until: datetime) -> Dict[str, Any]:
    rows = load_tickets_period(since, until)
    counters = count_opened_and_backlog(since, until)

    util_minutes = []
    corridas_minutes = []
    resolved_le_60min = 0
    outliers_gt_100h = 0

    by_prio = defaultdict(lambda: {"chamados": 0, "dentro": 0, "mins": []})
    weekly = defaultdict(lambda: {"volume": 0, "dentro": 0})

    for r in rows:
        opened = _parse_dt(r["data_abertura"])
        closed = _parse_dt(r["data_fechamento"])
        prio_label = PRIORITY_LABEL.get(r["prioridade_num"], "Média")
        sla_hours = SLA_HOURS_BY_PRIORITY[prio_label]
        mins_util = business_minutes_between(opened, closed)
        mins_corr = int((closed - opened).total_seconds() // 60)

        util_minutes.append(mins_util)
        corridas_minutes.append(mins_corr)
        if mins_util <= 60:
            resolved_le_60min += 1
        if mins_util > 100 * 60:
            outliers_gt_100h += 1

        by_prio[prio_label]["chamados"] += 1
        by_prio[prio_label]["mins"].append(mins_util)
        if mins_util <= sla_hours * 60:
            by_prio[prio_label]["dentro"] += 1

        year, week, _ = closed.isocalendar()
        weekly[(year, week)]["volume"] += 1
        if mins_util <= sla_hours * 60:
            weekly[(year, week)]["dentro"] += 1

    total_resolvidos = len(rows)
    mttr_mediano_util_h = round((median(util_minutes) / 60) if util_minutes else 0, 2)
    mttr_mediano_corrido_h = round((median(corridas_minutes) / 60) if corridas_minutes else 0, 2)
    mttr_medio_util_h = round((sum(util_minutes) / max(total_resolvidos, 1)) / 60, 2)
    mttr_medio_corrido_h = round((sum(corridas_minutes) / max(total_resolvidos, 1)) / 60, 2)
    pct_le_1h_util = round(100.0 * resolved_le_60min / max(total_resolvidos, 1), 1)

    dentro_total = sum(v["dentro"] for v in by_prio.values())
    compliance_overall = round(100.0 * dentro_total / max(total_resolvidos, 1), 1)
    taxa_resolucao = round(100.0 * counters["resolvidos_periodo"] / max(counters["abertos_periodo"], 1), 1)

    por_prioridade = []
    for label, v in by_prio.items():
        comp = round(100.0 * v["dentro"] / max(v["chamados"], 1), 1)
        med_util = round((median(v["mins"]) / 60) if v["mins"] else 0, 2)
        por_prioridade.append({
            "prioridade": label,
            "sla_h": SLA_HOURS_BY_PRIORITY[label],
            "chamados": v["chamados"],
            "dentro_sla": v["dentro"],
            "compliance_pct": comp,
            "mttr_mediano_util_h": med_util,
        })
    por_prioridade.sort(key=lambda x: ["Muito Alta","Alta","Média","Baixa","Muito Baixa"].index(x["prioridade"]) if x["prioridade"] in ["Muito Alta","Alta","Média","Baixa","Muito Baixa"] else 99)

    semanal = []
    for (year, week), wv in sorted(weekly.items()):
        comp = round(100.0 * wv["dentro"] / max(wv["volume"], 1), 1)
        monday = datetime.fromisocalendar(year, week, 1).date()
        sunday = datetime.fromisocalendar(year, week, 7).date()
        semanal.append({
            "semana": f"{year}-W{str(week).zfill(2)}",
            "inicio": str(monday),
            "fim": str(sunday),
            "volume": wv["volume"],
            "compliance_pct": comp,
        })

    return {
        "periodo": {"since": since.isoformat(), "until": until.isoformat()},
        "resumo": {
            "chamados_periodo": counters["abertos_periodo"],
            "resolvidos_periodo": counters["resolvidos_periodo"],
            "taxa_resolucao_pct": taxa_resolucao,
            "backlog": counters["backlog"],
            "sla_compliance_pct": compliance_overall,
            "mttr_mediano_util_h": mttr_mediano_util_h,
            "mttr_mediano_corrido_h": mttr_mediano_corrido_h,
            "mttr_medio_util_h": mttr_medio_util_h,
            "mttr_medio_corrido_h": mttr_medio_corrido_h,
            "resolvidos_le_1h_util_pct": pct_le_1h_util,
            "outliers_gt_100h": outliers_gt_100h,
        },
        "por_prioridade": por_prioridade,
        "semanal": semanal,
        "sla_padroes_h": SLA_HOURS_BY_PRIORITY,
    }


def _status_label(status: int) -> str:
    return {
        1: "Novo",
        2: "Em atendimento (atribuido)",
        3: "Em atendimento (planejado)",
        4: "Em espera",
        5: "Solucionado",
        6: "Fechado",
    }.get(status, "Outro")


def _as_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v))


def _now_like(sample: datetime | None) -> datetime:
    now = datetime.now(timezone.utc)
    if sample is None:
        return now.replace(tzinfo=None)
    if sample.tzinfo is None:
        return now.replace(tzinfo=None)
    return now.astimezone(sample.tzinfo)


def compute_open_sla_monitor(
    since: str | None = None,
    until: str | None = None,
    tech: str | None = None,
    category: str | None = None,
    priority: str | None = None,
) -> Dict[str, Any]:
    since_sql = None
    until_sql = None

    if since:
        since_dt = datetime.fromisoformat(str(since))
        if since_dt.tzinfo is not None:
            since_dt = since_dt.astimezone(timezone.utc).replace(tzinfo=None)
        since_sql = since_dt

    if until:
        until_dt = datetime.fromisoformat(str(until))
        if until_dt.tzinfo is not None:
            until_dt = until_dt.astimezone(timezone.utc).replace(tzinfo=None)
        # Inclui todo o dia final quando o filtro vier em YYYY-MM-DD.
        if len(str(until).strip()) <= 10:
            until_dt = until_dt + timedelta(days=1) - timedelta(seconds=1)
        until_sql = until_dt

    rows = execute_sql(
        """
        SELECT
          t.id AS ticket_id,
          t.name AS titulo,
          t.status AS status_num,
          t.priority AS prioridade_num,
          t.date AS data_abertura,
          t.time_to_resolve AS prazo_sla,
          COALESCE(cat.completename, 'Sem categoria') AS categoria,
          tut.users_id AS tecnico_id,
          CONCAT(ut.firstname, ' ', ut.realname) AS tecnico
        FROM glpi_tickets t
        LEFT JOIN glpi_itilcategories cat
               ON cat.id = t.itilcategories_id
        LEFT JOIN glpi_tickets_users tut
               ON tut.tickets_id = t.id AND tut.type = 2
        LEFT JOIN glpi_users ut
               ON ut.id = tut.users_id
        WHERE t.is_deleted = 0
          AND t.status NOT IN (5, 6)
          AND (%(since)s IS NULL OR t.date >= %(since)s)
          AND (%(until)s IS NULL OR t.date <= %(until)s)
        ORDER BY t.date ASC
        """,
        {"since": since_sql, "until": until_sql},
    )

    if not rows:
        return {
            "resumo": {
                "abertos_sem_solucao": 0,
                "com_atendimento_iniciado": 0,
                "sem_atendimento_iniciado": 0,
                "com_sla_definido": 0,
                "sem_sla_definido": 0,
                "alerta_70_pct": 0,
                "sla_estourado": 0,
            },
            "alertas": [],
            "abertos": [],
        }

    now = _now_like(_as_dt(rows[0].get("data_abertura")))
    alerts: List[Dict[str, Any]] = []
    open_rows: List[Dict[str, Any]] = []

    total_open = 0
    started = 0
    with_sla = 0
    without_sla = 0
    alert_70 = 0
    overdue = 0

    for r in rows:
        prio_label = PRIORITY_LABEL.get(int(r.get("prioridade_num") or 3), "Media")
        if tech and tech.strip() and tech.strip().lower() not in str(r.get("tecnico") or "").lower():
            continue
        if category and category.strip() and category.strip().lower() not in str(r.get("categoria") or "").lower():
            continue
        if priority and priority.strip() and priority.strip().lower() not in prio_label.lower():
            continue

        total_open += 1
        status_num = int(r.get("status_num") or 0)
        opened = _as_dt(r.get("data_abertura"))
        due = _as_dt(r.get("prazo_sla"))
        tech_assigned = r.get("tecnico_id") is not None

        started_flag = status_num in (2, 3, 4) or tech_assigned
        if started_flag:
            started += 1

        has_sla = due is not None
        if has_sla:
            with_sla += 1
        else:
            without_sla += 1

        sla_pct: float | None = None
        level = "sem_sla"
        opened_str = opened.isoformat(sep=" ")[:19] if opened else None
        due_str = due.isoformat(sep=" ")[:19] if due else None

        if opened and due:
            total_sla_util_min = business_minutes_between(opened, due)
            elapsed_util_min = business_minutes_between(opened, now)
            if total_sla_util_min <= 0:
                sla_pct = 100.0 if elapsed_util_min > 0 else 0.0
            else:
                sla_pct = round(100.0 * elapsed_util_min / total_sla_util_min, 1)

            if now > due:
                overdue += 1
                level = "critico"
            elif sla_pct >= 70.0:
                alert_70 += 1
                level = "alerta"
            else:
                level = "ok"

            if level in ("alerta", "critico"):
                alerts.append(
                    {
                        "ticket_id": r.get("ticket_id"),
                        "titulo": r.get("titulo"),
                        "status": _status_label(status_num),
                        "tecnico": (r.get("tecnico") or "").strip() or "Nao atribuido",
                        "sla_definido": True,
                        "data_abertura": opened_str,
                        "prazo_sla": due_str,
                        "sla_consumido_pct_util": sla_pct,
                        "nivel_alerta": level,
                    }
                )

        open_rows.append(
            {
                "ticket_id": r.get("ticket_id"),
                "titulo": r.get("titulo"),
                "status": _status_label(status_num),
                "tecnico": (r.get("tecnico") or "").strip() or "Nao atribuido",
                "categoria": r.get("categoria"),
                "prioridade": prio_label,
                "sla_definido": has_sla,
                "data_abertura": opened_str,
                "prazo_sla": due_str,
                "sla_consumido_pct_util": sla_pct,
                "nivel_alerta": level,
                "atendimento_iniciado": started_flag,
            }
        )

    alerts.sort(key=lambda x: x["sla_consumido_pct_util"], reverse=True)
    severity_rank = {"critico": 0, "alerta": 1, "ok": 2, "sem_sla": 3}
    open_rows.sort(
        key=lambda x: (
            severity_rank.get(str(x.get("nivel_alerta")), 9),
            -(x.get("sla_consumido_pct_util") or -1),
            str(x.get("data_abertura") or ""),
        )
    )

    return {
        "resumo": {
            "abertos_sem_solucao": total_open,
            "com_atendimento_iniciado": started,
            "sem_atendimento_iniciado": total_open - started,
            "com_sla_definido": with_sla,
            "sem_sla_definido": without_sla,
            "alerta_70_pct": alert_70,
            "sla_estourado": overdue,
        },
        "alertas": alerts[:50],
        "abertos": open_rows,
        "regras_horas_uteis": {
            "segunda_a_quinta": "08:00-12:00 e 13:00-18:00",
            "sexta": "08:00-12:00 e 13:00-17:00",
            "sabado_domingo": "sem expediente",
        },
    }


def _badge(value: float, good_min: float | None = None, good_max: float | None = None, warn_min: float | None = None, warn_max: float | None = None) -> str:
    if good_min is not None and value >= good_min:
        return "verde"
    if good_max is not None and value <= good_max:
        return "verde"
    if warn_min is not None and value >= warn_min:
        return "amarelo"
    if warn_max is not None and value <= warn_max:
        return "amarelo"
    return "vermelho"


def compute_management_pack(
    since: str | None = None,
    until: str | None = None,
    tech: str | None = None,
    category: str | None = None,
    priority: str | None = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if until:
        until_dt = datetime.fromisoformat(until)
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
    else:
        until_dt = now
    if since:
        since_dt = datetime.fromisoformat(since)
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
    else:
        since_dt = until_dt - timedelta(days=30)

    itil = compute_itil_metrics(since_dt, until_dt)
    open_sla = compute_open_sla_monitor(
        since=since_dt.date().isoformat(),
        until=until_dt.date().isoformat(),
        tech=tech,
        category=category,
        priority=priority,
    )

    resumo = itil.get("resumo", {})
    open_res = open_sla.get("resumo", {})
    weekly = itil.get("semanal", [])

    compliance = float(resumo.get("sla_compliance_pct") or 0.0)
    mttr_util_h = float(resumo.get("mttr_mediano_util_h") or 0.0)
    opened = float(resumo.get("chamados_periodo") or 0.0)
    resolved = float(resumo.get("resolvidos_periodo") or 0.0)
    throughput_pct = round((resolved / opened) * 100.0, 1) if opened > 0 else 0.0
    risk_alert = float(open_res.get("alerta_70_pct") or 0.0) + float(open_res.get("sla_estourado") or 0.0)
    with_sla = float(open_res.get("com_sla_definido") or 0.0)
    risk_pct = round((risk_alert / with_sla) * 100.0, 1) if with_sla > 0 else 0.0
    started = float(open_res.get("com_atendimento_iniciado") or 0.0)
    total_open = float(open_res.get("abertos_sem_solucao") or 0.0)
    started_pct = round((started / total_open) * 100.0, 1) if total_open > 0 else 0.0
    backlog_no_sla = float(open_res.get("sem_sla_definido") or 0.0)

    semaforos = [
        {
            "kpi": "Compliance SLA",
            "valor": compliance,
            "unidade": "%",
            "badge": _badge(compliance, good_min=90.0, warn_min=80.0),
            "meta": ">= 90%",
        },
        {
            "kpi": "MTTR mediano util",
            "valor": mttr_util_h,
            "unidade": "h",
            "badge": _badge(mttr_util_h, good_max=4.0, warn_max=8.0),
            "meta": "<= 4h",
        },
        {
            "kpi": "Risco SLA em abertos",
            "valor": risk_pct,
            "unidade": "%",
            "badge": _badge(risk_pct, good_max=10.0, warn_max=20.0),
            "meta": "<= 10%",
        },
        {
            "kpi": "Atendimento iniciado",
            "valor": started_pct,
            "unidade": "%",
            "badge": _badge(started_pct, good_min=85.0, warn_min=70.0),
            "meta": ">= 85%",
        },
        {
            "kpi": "Throughput",
            "valor": throughput_pct,
            "unidade": "%",
            "badge": _badge(throughput_pct, good_min=95.0, warn_min=85.0),
            "meta": ">= 95%",
        },
        {
            "kpi": "Abertos sem SLA",
            "valor": backlog_no_sla,
            "unidade": "",
            "badge": _badge(backlog_no_sla, good_max=0.0, warn_max=3.0),
            "meta": "0",
        },
    ]

    trend = weekly[-4:] if len(weekly) > 4 else weekly
    action_queue = []
    for row in open_sla.get("abertos", []):
        lvl = row.get("nivel_alerta")
        if lvl in ("critico", "alerta") or not row.get("atendimento_iniciado"):
            action_queue.append(row)

    rank = {"critico": 0, "alerta": 1, "ok": 2, "sem_sla": 3}
    action_queue.sort(
        key=lambda x: (
            rank.get(str(x.get("nivel_alerta")), 9),
            -(x.get("sla_consumido_pct_util") or -1),
            x.get("ticket_id") or 0,
        )
    )

    return {
        "periodo": {"since": since_dt.isoformat(), "until": until_dt.isoformat()},
        "semaforos": semaforos,
        "tendencia_semanal": trend,
        "fila_acao_imediata": action_queue[:50],
        "regras_horas_uteis": open_sla.get("regras_horas_uteis", {}),
    }


def _to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def compute_technician_kpis(
    since: str | None = None,
    until: str | None = None,
    tech: str | None = None,
    category: str | None = None,
    priority: str | None = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if until:
        until_dt = datetime.fromisoformat(str(until))
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
    else:
        until_dt = now
    if since:
        since_dt = datetime.fromisoformat(str(since))
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
    else:
        since_dt = until_dt - timedelta(days=90)

    since_sql = _to_naive_utc(since_dt)
    until_sql = _to_naive_utc(until_dt)

    resolved_rows = execute_sql(
        """
        SELECT
          t.id AS ticket_id,
          t.priority AS prioridade_num,
          t.date AS data_abertura,
          COALESCE(t.solvedate, t.closedate) AS data_fechamento,
          COALESCE(cat.completename, 'Sem categoria') AS categoria,
          CONCAT(u.firstname, ' ', u.realname) AS tecnico
        FROM glpi_tickets t
        LEFT JOIN (
          SELECT x.tickets_id, MAX(x.id) AS max_id
          FROM glpi_tickets_users x
          WHERE x.type = 2
          GROUP BY x.tickets_id
        ) tu_last
          ON tu_last.tickets_id = t.id
        LEFT JOIN glpi_tickets_users tu
          ON tu.id = tu_last.max_id
        LEFT JOIN glpi_users u
          ON u.id = tu.users_id
        LEFT JOIN glpi_itilcategories cat
          ON cat.id = t.itilcategories_id
        WHERE t.is_deleted = 0
          AND t.status IN (5, 6)
          AND COALESCE(t.solvedate, t.closedate) IS NOT NULL
          AND COALESCE(t.solvedate, t.closedate) BETWEEN %(since)s AND %(until)s
        """,
        {"since": since_sql, "until": until_sql},
    )

    open_rows_raw = execute_sql(
        """
        SELECT
          t.id AS ticket_id,
          t.priority AS prioridade_num,
          t.date AS data_abertura,
          t.time_to_resolve AS prazo_sla,
          COALESCE(cat.completename, 'Sem categoria') AS categoria,
          CONCAT(u.firstname, ' ', u.realname) AS tecnico
        FROM glpi_tickets t
        LEFT JOIN (
          SELECT x.tickets_id, MAX(x.id) AS max_id
          FROM glpi_tickets_users x
          WHERE x.type = 2
          GROUP BY x.tickets_id
        ) tu_last
          ON tu_last.tickets_id = t.id
        LEFT JOIN glpi_tickets_users tu
          ON tu.id = tu_last.max_id
        LEFT JOIN glpi_users u
          ON u.id = tu.users_id
        LEFT JOIN glpi_itilcategories cat
          ON cat.id = t.itilcategories_id
        WHERE t.is_deleted = 0
          AND t.status NOT IN (5, 6)
        """,
        {},
    )

    def _passes_filters(row: Dict[str, Any], prio_label: str) -> bool:
        tech_value = str(row.get("tecnico") or "").strip()
        category_value = str(row.get("categoria") or "").strip()
        if tech and tech.strip().lower() not in tech_value.lower():
            return False
        if category and category.strip().lower() not in category_value.lower():
            return False
        if priority and priority.strip().lower() not in prio_label.lower():
            return False
        return True

    by_tech: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "resolvidos_periodo": 0,
            "dentro_sla": 0,
            "mttr_util_min_list": [],
            "abertos_atuais": 0,
            "abertos_alerta_70": 0,
            "abertos_estourados": 0,
            "abertos_sem_sla": 0,
            "workload_total": 0,
        }
    )

    for r in resolved_rows:
        prio_label = PRIORITY_LABEL.get(int(r.get("prioridade_num") or 3), "Media")
        if not _passes_filters(r, prio_label):
            continue

        opened = _as_dt(r.get("data_abertura"))
        closed = _as_dt(r.get("data_fechamento"))
        if not opened or not closed:
            continue

        tech_name = (str(r.get("tecnico") or "").strip() or "Nao atribuido")
        mins_util = business_minutes_between(opened, closed)
        sla_h = SLA_HOURS_BY_PRIORITY.get(prio_label, 24)

        by_tech[tech_name]["resolvidos_periodo"] += 1
        by_tech[tech_name]["workload_total"] += 1
        by_tech[tech_name]["mttr_util_min_list"].append(mins_util)
        if mins_util <= sla_h * 60:
            by_tech[tech_name]["dentro_sla"] += 1

    for r in open_rows_raw:
        prio_label = PRIORITY_LABEL.get(int(r.get("prioridade_num") or 3), "Media")
        if not _passes_filters(r, prio_label):
            continue

        opened = _as_dt(r.get("data_abertura"))
        due = _as_dt(r.get("prazo_sla"))
        tech_name = (str(r.get("tecnico") or "").strip() or "Nao atribuido")
        by_tech[tech_name]["abertos_atuais"] += 1
        by_tech[tech_name]["workload_total"] += 1

        if not due:
            by_tech[tech_name]["abertos_sem_sla"] += 1
            continue

        if opened and due:
            total_sla_util_min = business_minutes_between(opened, due)
            elapsed_util_min = business_minutes_between(opened, _now_like(opened))
            sla_pct = 100.0 if total_sla_util_min <= 0 and elapsed_util_min > 0 else (
                round(100.0 * elapsed_util_min / total_sla_util_min, 1) if total_sla_util_min > 0 else 0.0
            )
            if _now_like(opened) > due:
                by_tech[tech_name]["abertos_estourados"] += 1
            elif sla_pct >= 70.0:
                by_tech[tech_name]["abertos_alerta_70"] += 1

    linhas: List[Dict[str, Any]] = []
    mttr_all: List[int] = []
    total_alerta = 0
    total_estourado = 0

    for tech_name, agg in by_tech.items():
        resolved_count = int(agg["resolvidos_periodo"])
        dentro = int(agg["dentro_sla"])
        compliance = round(100.0 * dentro / max(resolved_count, 1), 1) if resolved_count > 0 else None
        mttr_min_list = [int(x) for x in agg["mttr_util_min_list"]]
        mttr_med_min = int(median(mttr_min_list)) if mttr_min_list else None
        mttr_med_h = round((mttr_med_min / 60), 2) if mttr_med_min is not None else None
        mttr_hhmm = (
            f"{str(mttr_med_min // 60).zfill(2)}:{str(mttr_med_min % 60).zfill(2)}"
            if mttr_med_min is not None
            else "-"
        )

        if mttr_min_list:
            mttr_all.extend(mttr_min_list)
        total_alerta += int(agg["abertos_alerta_70"])
        total_estourado += int(agg["abertos_estourados"])

        linhas.append(
            {
                "tecnico": tech_name,
                "resolvidos_periodo": resolved_count,
                "dentro_sla_resolvidos": dentro,
                "compliance_sla_pct_util": compliance,
                "mttr_mediano_util_h": mttr_med_h,
                "mttr_mediano_util_hhmm": mttr_hhmm,
                "abertos_atuais": int(agg["abertos_atuais"]),
                "abertos_alerta_70": int(agg["abertos_alerta_70"]),
                "abertos_estourados": int(agg["abertos_estourados"]),
                "abertos_sem_sla": int(agg["abertos_sem_sla"]),
                "workload_total": int(agg["workload_total"]),
            }
        )

    linhas.sort(
        key=lambda x: (
            -(x.get("abertos_estourados") or 0),
            -(x.get("abertos_alerta_70") or 0),
            -((x.get("abertos_atuais") or 0)),
            x.get("tecnico") or "",
        )
    )

    tecnicos_ativos = len([l for l in linhas if l.get("workload_total", 0) > 0])
    equipe_mttr_min = int(median(mttr_all)) if mttr_all else None
    equipe_mttr_hhmm = (
        f"{str(equipe_mttr_min // 60).zfill(2)}:{str(equipe_mttr_min % 60).zfill(2)}"
        if equipe_mttr_min is not None
        else "-"
    )
    total_resolvidos_equipe = sum(int(l.get("resolvidos_periodo") or 0) for l in linhas)
    total_dentro_equipe = sum(int(l.get("dentro_sla_resolvidos") or 0) for l in linhas)
    equipe_compliance = round(
        100.0 * total_dentro_equipe / max(total_resolvidos_equipe, 1), 1
    ) if linhas else 0.0

    return {
        "periodo": {"since": since_dt.isoformat(), "until": until_dt.isoformat()},
        "resumo": {
            "tecnicos_ativos": tecnicos_ativos,
            "mttr_mediano_equipe_hhmm": equipe_mttr_hhmm,
            "alertas_70_abertos": total_alerta,
            "sla_estourado_abertos": total_estourado,
            "compliance_equipe_pct": equipe_compliance,
        },
        "linhas": linhas,
        "metas": {
            "compliance_sla_pct": ">= 90%",
            "mttr_mediano_util": "<= 04:00",
            "abertos_estourados": "0",
        },
    }
