-- ══════════════════════════════════════════════════════════
-- Q7 · MAPA DE INTERAÇÕES POR CHAMADO
-- Classifica chamados pelo número de trocas de mensagem
-- Identifica chamados problemáticos por má descrição inicial
-- ══════════════════════════════════════════════════════════
SELECT
    t.id                                           AS ticket_id,
    t.name                                         AS titulo,
    CONCAT(ut.firstname, ' ', ut.realname)         AS tecnico,
    CONCAT(ur.firstname, ' ', ur.realname)         AS requerente,
    COALESCE(loc.completename, 'N/I')              AS departamento,
    COALESCE(cat.completename, 'N/I')              AS categoria,
    COUNT(f.id)                                    AS total_followups,
    -- Followups do usuário requerente
    SUM(CASE WHEN f.users_id = tur.users_id
             THEN 1 ELSE 0 END)                   AS followups_usuario,
    -- Followups do técnico
    SUM(CASE WHEN f.users_id = tut.users_id
             THEN 1 ELSE 0 END)                   AS followups_tecnico,
    -- Tempo de resolução corrido
    ROUND(TIMESTAMPDIFF(MINUTE, t.date,
        COALESCE(t.solvedate, t.closedate)) / 60.0,
    2)                                             AS tempo_resolucao_h,
    -- Classificação da complexidade
    CASE
        WHEN COUNT(f.id) <= 1 THEN 'Simples (<=1 msg)'
        WHEN COUNT(f.id) BETWEEN 2 AND 4 THEN 'Moderado (2-4 msgs)'
        WHEN COUNT(f.id) BETWEEN 5 AND 9 THEN 'Complexo (5-9 msgs)'
        ELSE 'Problemático (10+ msgs)'
    END                                            AS classificacao_interacao
FROM glpi_tickets t
LEFT JOIN glpi_tickets_users tur
    ON tur.tickets_id = t.id AND tur.type = 1
LEFT JOIN glpi_users ur ON ur.id = tur.users_id
LEFT JOIN glpi_tickets_users tut
    ON tut.tickets_id = t.id AND tut.type = 2
LEFT JOIN glpi_users ut ON ut.id = tut.users_id
LEFT JOIN glpi_itilfollowups f
    ON f.items_id = t.id AND f.itemtype = 'Ticket'
    AND f.is_private = 0
LEFT JOIN glpi_itilcategories cat
    ON cat.id = t.itilcategories_id
LEFT JOIN glpi_locations loc
    ON loc.id = t.locations_id
WHERE t.is_deleted = 0
  AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
GROUP BY t.id, tur.users_id, tut.users_id
ORDER BY total_followups DESC;


