const el = (q) => document.querySelector(q);
const tokenKey = "glpi_token";
const loginView = el("#loginView");
const dashView = el("#dashboardView");
const logoutBtn = el("#logoutBtn");
const glpiTicketBaseUrl = (document.body.dataset.glpiTicketUrl || "").trim();
let currentView = "dash";
let lastGenericRows = [];
let charts = [];
const COLUMN_LABELS = {
  ticket_id: "Ticket",
  titulo: "Título",
  titulo_chamado: "Título",
  status: "Status",
  status_label: "Status",
  tecnico: "Técnico",
  atendimento_iniciado: "Atendimento iniciado",
  sla_definido: "SLA definido",
  data_abertura: "Data de abertura",
  data_followup: "Data do follow-up",
  prazo_sla: "Prazo SLA",
  sla_consumido_pct_util: "SLA consumido (%) útil",
  nivel_alerta: "Nível de alerta",
  prioridade: "Prioridade",
  prioridade_label: "Prioridade",
  categoria: "Categoria",
  departamento: "Departamento",
  requerente: "Requerente",
  autor: "Autor",
  usuario: "Usuário",
  compliance_pct: "Compliance (%)",
  compliance_sla_pct_util: "Compliance SLA (%) útil",
  mttr_mediano_util_h: "MTTR mediano (h úteis)",
  mttr_mediano_util: "MTTR mediano (HH:MM)",
  resolvidos_periodo: "Resolvidos no período",
  abertos_atuais: "Abertos atuais",
  alerta_70: "Alerta 70%",
  sla_estourado: "SLA estourado",
  abertos_sem_sla: "Abertos sem SLA",
  workload_total: "Carga total",
  semana: "Semana",
  volume: "Volume",
  dentro_sla: "Dentro do SLA",
  chamados: "Chamados",
  score_treinamento: "Score treinamento",
  qtd_chamados: "Qtd. chamados",
  total_chamados: "Total de chamados",
};

function normalizeHeaderLabel(key) {
  if (COLUMN_LABELS[key]) return COLUMN_LABELS[key];
  return String(key)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function parseSortValue(raw) {
  const txt = String(raw || "").trim().toLowerCase();
  if (!txt || txt === "-") return Number.NEGATIVE_INFINITY;
  const numericText = txt.replace("%", "").replace(",", ".");
  if (/^-?\d+(\.\d+)?$/.test(numericText)) return Number(numericText);
  if (/^\d{2}:\d{2}$/.test(txt)) {
    const [h, m] = txt.split(":").map(Number);
    return h * 60 + m;
  }
  const dateValue = Date.parse(txt);
  if (!Number.isNaN(dateValue)) return dateValue;
  return txt;
}

function enableTableSorting(scope = document) {
  scope.querySelectorAll("table.data-table").forEach((table) => {
    if (table.dataset.sortReady === "1") return;
    table.dataset.sortReady = "1";
    const headers = Array.from(table.querySelectorAll("thead th"));
    headers.forEach((th, idx) => {
      th.classList.add("sortable");
      th.addEventListener("click", () => {
        const tbody = table.tBodies[0];
        if (!tbody) return;
        const rows = Array.from(tbody.rows);
        const currentCol = Number(table.dataset.sortCol ?? "-1");
        const asc = currentCol === idx ? table.dataset.sortDir !== "asc" : true;
        rows.sort((a, b) => {
          const av = parseSortValue(a.cells[idx]?.textContent || "");
          const bv = parseSortValue(b.cells[idx]?.textContent || "");
          if (av === bv) return 0;
          if (typeof av === "number" && typeof bv === "number") return asc ? av - bv : bv - av;
          return asc
            ? String(av).localeCompare(String(bv), "pt-BR", { sensitivity: "base" })
            : String(bv).localeCompare(String(av), "pt-BR", { sensitivity: "base" });
        });
        rows.forEach((r) => tbody.appendChild(r));
        table.dataset.sortCol = String(idx);
        table.dataset.sortDir = asc ? "asc" : "desc";
        headers.forEach((h) => h.classList.remove("sorted-asc", "sorted-desc"));
        th.classList.add(asc ? "sorted-asc" : "sorted-desc");
      });
    });
  });
}

function setAuth(token) {
  if (token) localStorage.setItem(tokenKey, token);
}

function getAuth() {
  return localStorage.getItem(tokenKey);
}

function setLoginMode(enabled) {
  document.body.classList.toggle("login-mode", enabled);
}

function requireAuth() {
  const t = getAuth();
  if (!t || t === "null" || t === "undefined") {
    localStorage.removeItem(tokenKey);
    loginView.classList.remove("hidden");
    dashView.classList.add("hidden");
    setLoginMode(true);
    return null;
  }
  loginView.classList.add("hidden");
  dashView.classList.remove("hidden");
  setLoginMode(false);
  return t;
}

async function login(e) {
  e.preventDefault();
  const username = el("#username").value;
  const password = el("#password").value;
  const form = new URLSearchParams();
  form.set("username", username);
  form.set("password", password);
  form.set("grant_type", "password");

  const r = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  });

  if (!r.ok) {
    showToast("Falha no login.");
    return;
  }

  const data = await r.json();
  setAuth(data.access_token);
  requireAuth();
  navTo("dash");
  validateAllEndpoints();
}

function setStatusMessage(msg) {
  const bar = el("#statusMsg");
  if (bar) bar.textContent = msg;
  const stamp = el("#lastUpdated");
  if (stamp) stamp.textContent = `Atualizado: ${new Date().toLocaleString("pt-BR")}`;
}

function getFilters() {
  return {
    since: (el("#fltSince")?.value || "").trim(),
    until: (el("#fltUntil")?.value || "").trim(),
    tech: (el("#fltTech")?.value || "").trim().toLowerCase(),
    category: (el("#fltCategory")?.value || "").trim().toLowerCase(),
    priority: (el("#fltPriority")?.value || "").trim().toLowerCase(),
  };
}

function buildFilterQuery({ includeText = true } = {}) {
  const f = getFilters();
  const q = new URLSearchParams();
  if (f.since) q.set("since", f.since);
  if (f.until) q.set("until", f.until);
  if (includeText) {
    if (f.tech) q.set("tech", f.tech);
    if (f.category) q.set("category", f.category);
    if (f.priority) q.set("priority", f.priority);
  }
  return q.toString();
}

function hasActiveFilters(f) {
  return !!(f.since || f.until || f.tech || f.category || f.priority);
}

function updateFiltersInfo() {
  const f = getFilters();
  const active = [];
  if (f.since) active.push(`de ${f.since}`);
  if (f.until) active.push(`até ${f.until}`);
  if (f.tech) active.push(`técnico: ${f.tech}`);
  if (f.category) active.push(`categoria: ${f.category}`);
  if (f.priority) active.push(`prioridade: ${f.priority}`);
  el("#filtersInfo").textContent = active.length ? `Filtros ativos: ${active.join(" | ")}` : "Sem filtros ativos";
}

function parseDateLoose(v) {
  if (v == null) return null;
  const s = String(v).trim();
  if (!s) return null;
  const d = new Date(s);
  if (!Number.isNaN(d.getTime())) return d;
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return new Date(`${m[1]}-${m[2]}-${m[3]}T00:00:00`);
  return null;
}

function includesAny(row, keys, term) {
  if (!term) return true;
  const values = keys.map((k) => row[k]).filter((v) => v != null);
  if (!values.length) return true;
  return values.some((v) => String(v).toLowerCase().includes(term));
}

function applyGlobalFilters(rows) {
  const f = getFilters();
  if (!Array.isArray(rows) || !hasActiveFilters(f)) return Array.isArray(rows) ? rows : [];
  const since = f.since ? new Date(`${f.since}T00:00:00`) : null;
  const until = f.until ? new Date(`${f.until}T23:59:59`) : null;

  return rows.filter((row) => {
    const dateKeys = ["data_abertura", "data_followup", "abertura_chamado", "data_inicio", "inicio", "date"];
    const firstDateKey = dateKeys.find((k) => row[k] != null);
    if (firstDateKey) {
      const d = parseDateLoose(row[firstDateKey]);
      if (since && d && d < since) return false;
      if (until && d && d > until) return false;
    }

    if (!includesAny(row, ["tecnico", "autor", "usuario"], f.tech)) return false;
    if (!includesAny(row, ["categoria", "categoria_nivel1", "top_categoria"], f.category)) return false;
    if (!includesAny(row, ["prioridade", "prioridade_label", "prioridade_selecionada"], f.priority)) return false;
    return true;
  });
}

function showToast(msg) {
  const t = el("#toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 3500);
}

function setOffline(flag, text = "Dados indisponíveis no momento.") {
  const b = el("#offlineBanner");
  if (!b) return;
  if (flag) {
    b.textContent = text;
    b.classList.remove("hidden");
  } else {
    b.classList.add("hidden");
  }
}

async function authedFetch(url, timeoutMs = 15000) {
  const token = getAuth();
  if (!token || token === "null" || token === "undefined") throw new Error("NO_TOKEN");
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    return await fetch(url, { headers: { Authorization: `Bearer ${token}` }, signal: ac.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function authedFetchJSON(url, expected = "array", attempts = 3, baseDelay = 400) {
  let last = { ok: false, code: 0, data: null, error: "Falha" };
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await authedFetch(url);
      const code = res.status;
      let data = null;
      try {
        data = await res.json();
      } catch {
        data = null;
      }

      let ok = res.ok;
      if (expected === "array") ok = ok && Array.isArray(data);
      if (expected === "object") ok = ok && data && typeof data === "object" && !Array.isArray(data);

      if (code === 401) {
        localStorage.removeItem(tokenKey);
        requireAuth();
        showToast("Sessão expirada. Faça login novamente.");
      }

      const count = Array.isArray(data) ? data.length : data ? 1 : 0;
      last = { ok, code, data, count, error: ok ? null : "Formato invalido ou erro HTTP" };
      if (ok || code === 401) break;
    } catch (err) {
      if (err && err.message === "NO_TOKEN") {
        requireAuth();
        return { ok: false, code: 401, data: null, count: 0, error: "Sem token" };
      }
      last = { ok: false, code: 0, data: null, count: 0, error: err.message || "Falha de rede" };
    }
    await new Promise((r) => setTimeout(r, baseDelay * Math.pow(2, i)));
  }
  return last;
}

function updateEndpointStatus(list) {
  const c = el("#endpointStatus");
  if (!c) return;
  c.innerHTML = list
    .map((it) => {
      const cls = it.ok ? "ok" : it.code ? "warn" : "err";
      const suffix = it.ok ? ` · ${it.count}` : it.code ? ` · ${it.code}` : "";
      return `<span class="chip"><span class="dot ${cls}"></span>${it.name}${suffix}</span>`;
    })
    .join("");
}

async function validateAllEndpoints() {
  if (!getAuth()) {
    requireAuth();
    showToast("Faça login para validar os endpoints.");
    updateEndpointStatus([]);
    setStatusMessage("Aguardando login");
    return;
  }

  const items = [
    { name: "Dashboard", url: "/kpis/dashboard-semanal", expected: "array" },
    { name: "Heatmap", url: "/kpis/heatmap", expected: "array" },
    { name: "Reincidência", url: "/kpis/reincidencia", expected: "array" },
    { name: "Score Dep.", url: "/kpis/score-departamento", expected: "array" },
    { name: "First Response", url: "/kpis/first-response-time", expected: "array" },
    { name: "Interações", url: "/kpis/interacoes", expected: "array" },
    { name: "Problemas ITIL", url: "/kpis/problemas-itil", expected: "array" },
    { name: "Recorrentes", url: "/kpis/recorrentes-impacto", expected: "array" },
    { name: "Ranking", url: "/kpis/ranking-usuarios-treinamento", expected: "array" },
    { name: "Base", url: "/kpis/base", expected: "array" },
    { name: "Follow-ups", url: "/kpis/followups", expected: "array" },
    { name: "Qualidade", url: "/kpis/qualidade-abertura", expected: "array" },
    { name: "ITIL Summary", url: "/metrics/itil-summary", expected: "object" },
    { name: "Open SLA", url: "/metrics/open-sla-monitor", expected: "object" },
    { name: "Management", url: "/metrics/management-pack", expected: "object" },
    { name: "Técnicos KPIs", url: "/metrics/tecnicos-kpis", expected: "object" },
  ];

  setStatusMessage("Validando endpoints...");
  const results = await Promise.all(
    items.map(async (it) => {
      const r = await authedFetchJSON(it.url, it.expected, 3, 350);
      return { name: it.name, ok: r.ok, code: r.code, count: r.count || 0 };
    }),
  );
  updateEndpointStatus(results);
  const okCount = results.filter((r) => r.ok).length;
  setStatusMessage(`Validação concluída: ${okCount}/${results.length} OK`);

  let dbHealthy = true;
  try {
    const healthRes = await fetch("/health?details=1");
    if (healthRes.ok) {
      const health = await healthRes.json();
      dbHealthy = !!(health && health.db && health.db.ok);
    }
  } catch {
    dbHealthy = true;
  }

  const coreEndpoints = new Set(["Dashboard", "ITIL Summary", "Open SLA", "Management", "Técnicos KPIs"]);
  const coreResults = results.filter((r) => coreEndpoints.has(r.name));
  const coreOkCount = coreResults.filter((r) => r.ok).length;
  const coreFailed = coreResults.length > 0 && coreOkCount < coreResults.length;

  const showOfflineBanner = !dbHealthy || (coreFailed && okCount === 0);
  setOffline(showOfflineBanner, "Dados indisponíveis. Verifique conexão com banco.");
}

function destroyCharts() {
  charts.forEach((c) => c.destroy());
  charts = [];
}

function formatHoursToHHMM(value) {
  const hours = Number(value);
  if (!Number.isFinite(hours) || hours < 0) return "-";
  const totalMinutes = Math.round(hours * 60);
  const hh = Math.floor(totalMinutes / 60);
  const mm = totalMinutes % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

function formatDateTimePtBr(value) {
  if (value == null) return "-";
  const raw = String(value).trim();
  if (!raw) return "-";
  const d = parseDateLoose(raw);
  if (!d) return raw;
  return d.toLocaleString("pt-BR");
}

function tableHTML(rows, columns, emptyText = "Nenhum dado para o período selecionado.") {
  if (!Array.isArray(rows) || rows.length === 0) return `<p>${emptyText}</p>`;
  const cols = columns && columns.length ? columns : Object.keys(rows[0]);
  const thead = "<thead><tr>" + cols.map((c) => `<th data-key=\"${c}\">${normalizeHeaderLabel(c)}</th>`).join("") + "</tr></thead>";
  const tbody =
    "<tbody>" +
    rows.map((r) => "<tr>" + cols.map((c) => `<td>${r[c] ?? ""}</td>`).join("") + "</tr>").join("") +
    "</tbody>";
  return `<div class="table-wrap"><table class="data-table">${thead}${tbody}</table></div>`;
}

function decorateRowsWithTicketLinks(rows) {
  if (!Array.isArray(rows)) return [];
  return rows.map((row) => {
    if (!row || typeof row !== "object") return row;
    const out = { ...row };
    if (Object.prototype.hasOwnProperty.call(out, "ticket_id")) {
      out.ticket_id = formatTicketLink(out.ticket_id);
    }
    return out;
  });
}

function renderHeatmap(rows) {
  const safeRows = Array.isArray(rows) ? rows : [];
  const labels = [...new Set(safeRows.map((r) => r.dia_semana))];
  const totals = labels.map((l) =>
    safeRows.filter((r) => r.dia_semana === l).reduce((acc, r) => acc + (r.total_chamados || 0), 0),
  );
  const canvas = document.getElementById("heatmapChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  charts.push(
    new Chart(ctx, {
      type: "bar",
      data: { labels, datasets: [{ label: "Chamados", data: totals, backgroundColor: "#2563eb" }] },
      options: { responsive: true, plugins: { legend: { display: false } } },
    }),
  );
}

function renderItilSummary(data) {
  if (!data || !data.resumo) return;
  const r = data.resumo;
  el("#mttrMedianoUtil").textContent = formatHoursToHHMM(r.mttr_mediano_util_h);
  el("#outliers").textContent = r.outliers_gt_100h ?? "-";
  el("#taxaResolucao").textContent = r.taxa_resolucao_pct != null ? `${r.taxa_resolucao_pct}%` : "-";
  el("#slaPrioridade").innerHTML = tableHTML(
    data.por_prioridade,
    ["prioridade", "sla_h", "chamados", "dentro_sla", "compliance_pct", "mttr_mediano_util_h"],
  );
  enableTableSorting(el("#slaPrioridade"));

  const canvas = document.getElementById("weeklyChart");
  if (!canvas) return;
  const labels = (data.semanal || []).map((w) => w.semana);
  const comp = (data.semanal || []).map((w) => w.compliance_pct);
  charts.push(
    new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Compliance SLA (%)",
          data: comp,
          borderColor: "#1d4ed8",
          backgroundColor: "rgba(29, 78, 216, 0.16)",
          tension: 0.25,
        }],
      },
      options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { min: 0, max: 100 } } },
    }),
  );
}

function renderOpenSlaMonitor(data) {
  if (!data || !data.resumo) return;
  const r = data.resumo;
  const openTotal = Number(r.abertos_sem_solucao || 0);
  const openStarted = Number(r.com_atendimento_iniciado || 0);
  const openNotStarted = Number(r.sem_atendimento_iniciado || 0);
  const withSla = Number(r.com_sla_definido || 0);
  const alert70 = Number(r.alerta_70_pct || 0);
  const overdue = Number(r.sla_estourado || 0);

  el("#kpiOpenTotal").textContent = openTotal;
  el("#kpiOpenStarted").textContent = openStarted;
  el("#kpiOpenNotStarted").textContent = openNotStarted;
  el("#kpiOpenWithSla").textContent = withSla;
  el("#kpiOpenAlert70").textContent = alert70;
  el("#kpiOpenOverdue").textContent = overdue;

  el("#kpiOpenAlert70").classList.toggle("alert", alert70 > 0);
  el("#kpiOpenOverdue").classList.toggle("critical", overdue > 0);

  const rules = data.regras_horas_uteis || {};
  el("#openSlaRules").textContent =
    `Regra útil: Seg-Qui ${rules.segunda_a_quinta || "08:00-12:00 e 13:00-18:00"} | Sex ${rules.sexta || "08:00-12:00 e 13:00-17:00"}`;

  const allOpen = applyGlobalFilters(Array.isArray(data.abertos) ? data.abertos : []);
  if (!allOpen.length) {
    el("#openSlaAlerts").innerHTML = "<p>Nenhum chamado aberto sem solução no momento.</p>";
    return;
  }

  const rows = allOpen.map((a) => ({
    ticket_id: formatTicketLink(a.ticket_id),
    titulo: a.titulo,
    status: a.status,
    tecnico: a.tecnico,
    atendimento_iniciado: a.atendimento_iniciado ? "Sim" : "Não",
    sla_definido: a.sla_definido ? "Sim" : "Não",
    data_abertura: formatDateTimePtBr(a.data_abertura),
    prazo_sla: formatDateTimePtBr(a.prazo_sla),
    sla_consumido_pct_util:
      a.sla_consumido_pct_util == null ? "-" : `${a.sla_consumido_pct_util}%`,
    nivel_alerta: a.nivel_alerta === "critico"
      ? '<span class="pill critical">Crítico</span>'
      : a.nivel_alerta === "alerta"
        ? '<span class="pill alert">Alerta 70%</span>'
        : a.nivel_alerta === "ok"
          ? '<span class="pill ok">Dentro do SLA</span>'
          : '<span class="pill semsla">Sem SLA</span>',
  }));

  const cols = [
    "ticket_id",
    "titulo",
    "status",
    "tecnico",
    "atendimento_iniciado",
    "sla_definido",
    "data_abertura",
    "prazo_sla",
    "sla_consumido_pct_util",
    "nivel_alerta",
  ];

  el("#openSlaAlerts").innerHTML = tableHTML(rows, cols);
  enableTableSorting(el("#openSlaAlerts"));
}

function renderManagementPack(data) {
  if (!data) return;
  const sem = Array.isArray(data.semaforos) ? data.semaforos : [];
  const semArea = el("#execSemaforos");
  semArea.innerHTML = sem
    .map((s) => {
      const badgeCls = s.badge === "verde" ? "exec-ok" : s.badge === "amarelo" ? "exec-warn" : "exec-critical";
      const unit = s.unidade || "";
      const valueText = String(s.kpi || "").toLowerCase().includes("mttr")
        ? formatHoursToHHMM(s.valor)
        : `${s.valor}${unit}`;
      return `
        <div class="card exec-card">
          <div class="exec-kpi">${s.kpi}</div>
          <div class="exec-val ${badgeCls}">${valueText}</div>
          <div class="exec-meta">Meta: ${s.meta}</div>
        </div>
      `;
    })
    .join("");

  const trend = Array.isArray(data.tendencia_semanal) ? data.tendencia_semanal : [];
  el("#execTrend").innerHTML = tableHTML(trend, ["semana", "volume", "compliance_pct"], "Sem tendência semanal.");
  enableTableSorting(el("#execTrend"));
  const split = document.querySelector(".exec-split");
  split?.classList.toggle("queue-only", trend.length === 0);

  const queue = Array.isArray(data.fila_acao_imediata) ? data.fila_acao_imediata : [];
  const queueRows = queue.map((q) => ({
    ticket_id: formatTicketLink(q.ticket_id),
    titulo: q.titulo,
    status: q.status,
    tecnico: q.tecnico,
    sla_consumido_pct_util: q.sla_consumido_pct_util == null ? "-" : `${q.sla_consumido_pct_util}%`,
    nivel_alerta:
      q.nivel_alerta === "critico"
        ? '<span class="pill critical">Crítico</span>'
        : q.nivel_alerta === "alerta"
          ? '<span class="pill alert">Alerta</span>'
          : '<span class="pill semsla">Sem SLA</span>',
  }));
  const cols = ["ticket_id", "titulo", "status", "tecnico", "sla_consumido_pct_util", "nivel_alerta"];
  if (!queueRows.length) {
    el("#execQueue").innerHTML = "<p>Nenhum item em fila de ação imediata.</p>";
  } else {
    el("#execQueue").innerHTML = tableHTML(queueRows, cols);
    enableTableSorting(el("#execQueue"));
  }
}

function renderTechnicianKpis(data) {
  if (!data || !data.resumo) return;
  const r = data.resumo;
  const compliance = Number(r.compliance_equipe_pct || 0);
  const alert70 = Number(r.alertas_70_abertos || 0);
  const overdue = Number(r.sla_estourado_abertos || 0);

  el("#kpiTechAtivos").textContent = r.tecnicos_ativos ?? "-";
  el("#kpiTechMttrEquipe").textContent = r.mttr_mediano_equipe_hhmm || "-";
  el("#kpiTechComplianceEquipe").textContent = r.compliance_equipe_pct != null ? `${r.compliance_equipe_pct}%` : "-";
  el("#kpiTechAlertas70").textContent = alert70;
  el("#kpiTechSlaEstourado").textContent = overdue;

  el("#kpiTechComplianceEquipe").classList.toggle("alert", compliance < 90 && compliance >= 80);
  el("#kpiTechComplianceEquipe").classList.toggle("critical", compliance < 80);
  el("#kpiTechAlertas70").classList.toggle("alert", alert70 > 0);
  el("#kpiTechSlaEstourado").classList.toggle("critical", overdue > 0);

  const metas = data.metas || {};
  el("#techKpiRules").textContent =
    `Metas: Compliance ${metas.compliance_sla_pct || ">= 90%"} | MTTR ${metas.mttr_mediano_util || "<= 04:00"} | SLA estourado ${metas.abertos_estourados || "0"}`;

  const rowsRaw = applyGlobalFilters(Array.isArray(data.linhas) ? data.linhas : []);
  if (!rowsRaw.length) {
    el("#techKpiTable").innerHTML = "<p>Nenhum técnico com dados no período/filtro atual.</p>";
    return;
  }

  const rows = rowsRaw.map((t) => ({
    tecnico: t.tecnico || "-",
    resolvidos_periodo: t.resolvidos_periodo ?? 0,
    compliance_sla_pct_util: t.compliance_sla_pct_util == null ? "-" : `${t.compliance_sla_pct_util}%`,
    mttr_mediano_util: t.mttr_mediano_util_hhmm || "-",
    abertos_atuais: t.abertos_atuais ?? 0,
    alerta_70: t.abertos_alerta_70 ?? 0,
    sla_estourado: t.abertos_estourados ?? 0,
    abertos_sem_sla: t.abertos_sem_sla ?? 0,
    workload_total: t.workload_total ?? 0,
  }));

  const cols = [
    "tecnico",
    "resolvidos_periodo",
    "compliance_sla_pct_util",
    "mttr_mediano_util",
    "abertos_atuais",
    "alerta_70",
    "sla_estourado",
    "abertos_sem_sla",
    "workload_total",
  ];

  el("#techKpiTable").innerHTML = tableHTML(rows, cols);
  enableTableSorting(el("#techKpiTable"));
}

function formatTicketLink(ticketId) {
  if (ticketId == null) return "-";
  const id = String(ticketId);
  if (!glpiTicketBaseUrl) return id;
  const base = glpiTicketBaseUrl.endsWith("=") || glpiTicketBaseUrl.endsWith("/")
    ? glpiTicketBaseUrl
    : `${glpiTicketBaseUrl}${glpiTicketBaseUrl.includes("?") ? "&id=" : "?id="}`;
  const href = `${base}${encodeURIComponent(id)}`;
  return `<a href="${href}" target="_blank" rel="noopener noreferrer">${id}</a>`;
}

function tableToCsv(table) {
  const rows = Array.from(table.querySelectorAll("tr"));
  return rows
    .map((row) =>
      Array.from(row.querySelectorAll("th,td"))
        .map((cell) => {
          const text = (cell.textContent || "").replace(/\s+/g, " ").trim();
          const escaped = text.replace(/"/g, '""');
          return `"${escaped}"`;
        })
        .join(","),
    )
    .join("\n");
}

function exportVisibleTableCsv() {
  const genericVisible = !el("#view-generic")?.classList.contains("hidden");
  const dashVisible = !el("#view-dash")?.classList.contains("hidden");
  let table = null;
  if (genericVisible) {
    table = el("#genericArea table");
  } else if (dashVisible) {
    table = el("#openSlaAlerts table") || el("#slaPrioridade table");
  } else {
    table = document.querySelector("table");
  }
  if (!table) {
    showToast("Nenhuma tabela visível para exportar.");
    return;
  }
  const csv = tableToCsv(table);
  const active = document.querySelector(".tab.active")?.dataset.view || "dados";
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  const f = getFilters();
  const clean = (x) => String(x || "").replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 18);
  const parts = [active];
  if (f.since || f.until) parts.push(`${clean(f.since || "inicio")}-${clean(f.until || "hoje")}`);
  if (f.tech) parts.push(`tec-${clean(f.tech)}`);
  if (f.category) parts.push(`cat-${clean(f.category)}`);
  if (f.priority) parts.push(`prio-${clean(f.priority)}`);
  const filename = `glpi-${parts.filter(Boolean).join("-")}-${stamp}.csv`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function loadDashboard() {
  try {
    setStatusMessage("Carregando dashboard...");
    const itilQ = buildFilterQuery({ includeText: false });
    const allQ = buildFilterQuery({ includeText: true });
    const itilUrl = itilQ ? `/metrics/itil-summary?${itilQ}` : "/metrics/itil-summary";
    const heatmapUrl = allQ ? `/kpis/heatmap?${allQ}` : "/kpis/heatmap";
    const openSlaUrl = allQ ? `/metrics/open-sla-monitor?${allQ}` : "/metrics/open-sla-monitor";
    const mgmtUrl = allQ ? `/metrics/management-pack?${allQ}` : "/metrics/management-pack";
    const techKpiUrl = allQ ? `/metrics/tecnicos-kpis?${allQ}` : "/metrics/tecnicos-kpis";

    const dashRes = await authedFetchJSON("/kpis/dashboard-semanal", "array", 3, 300);
    const first = dashRes.ok && dashRes.data[0] ? dashRes.data[0] : {};
    el("#kpiAbertos").textContent = first.total_abertos ?? "-";
    el("#kpiFechados").textContent = first.total_fechados ?? "-";
    el("#kpiSLA").textContent = first.pct_compliance != null ? `${first.pct_compliance}%` : "-";
    destroyCharts();
    renderHeatmap((await authedFetchJSON(heatmapUrl, "array", 3, 300)).data || []);
    const itilRes = await authedFetchJSON(itilUrl, "object", 3, 300);
    if (itilRes.ok) renderItilSummary(itilRes.data);
    const openSlaRes = await authedFetchJSON(openSlaUrl, "object", 3, 300);
    if (openSlaRes.ok) renderOpenSlaMonitor(openSlaRes.data);
    const mgmtRes = await authedFetchJSON(mgmtUrl, "object", 3, 300);
    if (mgmtRes.ok) renderManagementPack(mgmtRes.data);
    const techRes = await authedFetchJSON(techKpiUrl, "object", 3, 300);
    if (techRes.ok) renderTechnicianKpis(techRes.data);
    updateFiltersInfo();
    setStatusMessage("Dashboard atualizado");
  } catch (e) {
    console.error(e);
    setStatusMessage("Erro ao carregar dashboard");
    showToast("Erro ao carregar dados do dashboard.");
  }
}

function setActiveTab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
}

function viewMap(view) {
  if (view === "reincidencia") return { url: "/kpis/reincidencia", cols: ["requerente", "categoria", "qtd_chamados", "intervalo_dias", "ids_chamados"] };
  if (view === "score") return { url: "/kpis/score-departamento", cols: ["departamento", "total_chamados", "pct_titulo_ruim", "pct_sem_descricao", "pct_caps_lock"] };
  if (view === "frt") return { url: "/kpis/first-response-time", cols: ["ticket_id", "titulo", "tecnico", "hrs_ate_primeiro_contato", "respondeu_em_1h", "prioridade"] };
  if (view === "interacoes") return { url: "/kpis/interacoes", cols: ["ticket_id", "titulo", "tecnico", "requerente", "total_followups", "followups_usuario", "followups_tecnico", "tempo_resolucao_h"] };
  if (view === "problemas") return { url: "/kpis/problemas-itil", cols: ["problema_id", "titulo_problema", "status_problema", "categoria", "qtd_incidentes_vinculados", "total_horas_incidentes", "ids_chamados_vinculados"] };
  if (view === "recorrentes") return { url: "/kpis/recorrentes-impacto", cols: ["nome_recorrente", "ativo", "periodicidade_dias", "data_inicio", "qtd_gerados_90d", "projecao_anual", "total_horas_corridas", "media_horas_por_chamado"] };
  if (view === "ranking") return { url: "/kpis/ranking-usuarios-treinamento", cols: ["usuario", "departamento", "total_chamados", "score_treinamento"] };
  if (view === "base") return { url: "/kpis/base", cols: ["ticket_id", "titulo", "status_label", "prioridade_label", "data_abertura", "tecnico", "requerente", "categoria"] };
  if (view === "followups") return { url: "/kpis/followups", cols: ["ticket_id", "titulo_chamado", "data_followup", "autor", "conteudo", "qtd_palavras_estimada", "canal_origem"] };
  if (view === "qualidade") return { url: "/kpis/qualidade-abertura", cols: ["ticket_id", "autor", "departamento", "categoria", "titulo", "qualidade_titulo", "qualidade_descricao", "titulo_em_caps_lock", "tem_numero_referencia", "qtd_trocas_mensagens"] };
  return { url: "", cols: [] };
}

async function navTo(view) {
  currentView = view;
  setActiveTab(view);
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));

  if (view === "dash") {
    el("#view-dash").classList.remove("hidden");
    await loadDashboard();
    return;
  }

  if (view === "heatmap") {
    el("#view-heatmap").classList.remove("hidden");
    destroyCharts();
    const q = buildFilterQuery({ includeText: true });
    const heatUrl = q ? `/kpis/heatmap?${q}` : "/kpis/heatmap";
    const heatRes = await authedFetchJSON(heatUrl, "array", 3, 300);
    renderHeatmap(heatRes.ok ? heatRes.data : []);
    return;
  }

  el("#view-generic").classList.remove("hidden");
  const area = el("#genericArea");
  area.classList.add("loading");
  area.textContent = "Carregando...";

  const conf = viewMap(view);
  const q = buildFilterQuery({ includeText: true });
  const url = q ? `${conf.url}?${q}` : conf.url;
  const res = await authedFetchJSON(url, "array", 3, 300);
  const emptyInfo = `Sem registros para "${view}" na janela atual de consulta.`;
  const filtered = applyGlobalFilters(res.ok ? res.data : []);
  lastGenericRows = filtered;
  const linkedRows = decorateRowsWithTicketLinks(filtered);
  area.innerHTML = tableHTML(linkedRows, conf.cols, emptyInfo);
  enableTableSorting(area);
  updateFiltersInfo();
  area.classList.remove("loading");
}

el("#loginForm").addEventListener("submit", login);
logoutBtn.addEventListener("click", () => {
  localStorage.removeItem(tokenKey);
  requireAuth();
});
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => navTo(b.dataset.view)));
document.getElementById("btnRefresh")?.addEventListener("click", () => navTo(document.querySelector(".tab.active")?.dataset.view || "dash"));
document.getElementById("btnValidate")?.addEventListener("click", validateAllEndpoints);
document.getElementById("btnExport")?.addEventListener("click", exportVisibleTableCsv);
document.getElementById("btnExportGeneric")?.addEventListener("click", exportVisibleTableCsv);
document.getElementById("btnApplyFilters")?.addEventListener("click", () => navTo(currentView));
document.getElementById("btnClearFilters")?.addEventListener("click", () => {
  el("#fltSince").value = "";
  el("#fltUntil").value = "";
  el("#fltTech").value = "";
  el("#fltCategory").value = "";
  el("#fltPriority").value = "";
  updateFiltersInfo();
  navTo(currentView);
});

if (requireAuth()) {
  navTo("dash");
  validateAllEndpoints();
}



