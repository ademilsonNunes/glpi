-- ══════════════════════════════════════════════════════════
-- Q1 · EXTRAÇÃO BASE: TODOS OS CHAMADOS COM METADADOS
-- GLPI 10.x · MySQL/MariaDB
-- Ajuste: janela padrao dos ultimos 365 dias
-- ══════════════════════════════════════════════════════════
SELECT
    t.id                                           AS ticket_id,
    t.name                                         AS titulo,
    CASE t.status
        WHEN 1 THEN 'Novo'
        WHEN 2 THEN 'Em atendimento (atribuído)'
        WHEN 3 THEN 'Em atendimento (planejado)'
        WHEN 4 THEN 'Em espera'
        WHEN 5 THEN 'Solucionado'
        WHEN 6 THEN 'Fechado'
    END                                            AS status_label,
    CASE t.priority
        WHEN 1 THEN 'Muito Baixa'
        WHEN 2 THEN 'Baixa'
        WHEN 3 THEN 'Média'
        WHEN 4 THEN 'Alta'
        WHEN 5 THEN 'Muito Alta'
        WHEN 6 THEN 'Crítica'
    END                                            AS prioridade_label,
    t.priority                                     AS prioridade_num,
    t.date                                         AS data_abertura,
    t.closedate                                    AS data_fechamento,
    t.solvedate                                    AS data_solucao,
    t.time_to_resolve                              AS sla_prazo_glpi,
    -- Tempo total corrido em horas (24x7)
    ROUND(TIMESTAMPDIFF(MINUTE, t.date,
        COALESCE(t.solvedate, t.closedate)) / 60, 2)
                                                   AS tempo_corrido_horas,
    -- Requerente
    CONCAT(ur.firstname, ' ', ur.realname)         AS requerente,
    -- Técnico atribuído (primeiro da lista)
    CONCAT(ut.firstname, ' ', ut.realname)         AS tecnico,
    -- Categoria
    COALESCE(cat.completename, 'Sem categoria')    AS categoria,
    cat.name                                       AS categoria_nivel1,
    -- Localização / Departamento
    COALESCE(loc.completename, 'Não informado')    AS localizacao,
    -- Flags de SLA GLPI nativo
    t.sla_waiting_duration                         AS sla_tempo_espera_seg,
    CASE WHEN t.time_to_resolve IS NOT NULL
         AND COALESCE(t.solvedate, t.closedate) > t.time_to_resolve
         THEN 1 ELSE 0
    END                                            AS sla_violado_glpi,
    -- Contagem de atualizações (proxy de interações)
    (SELECT COUNT(*) FROM glpi_itilfollowups f
     WHERE f.items_id = t.id AND f.itemtype = 'Ticket')
                                                   AS qtd_followups,
    (SELECT COUNT(*) FROM glpi_tickettasks tk
     WHERE tk.tickets_id = t.id)                  AS qtd_tarefas,
    t.entities_id                                  AS entidade_id
FROM glpi_tickets t
-- Requerente
LEFT JOIN glpi_tickets_users tur
    ON tur.tickets_id = t.id AND tur.type = 1
LEFT JOIN glpi_users ur
    ON ur.id = tur.users_id
-- Técnico
LEFT JOIN glpi_tickets_users tut
    ON tut.tickets_id = t.id AND tut.type = 2
LEFT JOIN glpi_users ut
    ON ut.id = tut.users_id
-- Categoria
LEFT JOIN glpi_itilcategories cat
    ON cat.id = t.itilcategories_id
-- Localização
LEFT JOIN glpi_locations loc
    ON loc.id = t.locations_id
WHERE t.is_deleted = 0
  AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
ORDER BY t.date DESC;

