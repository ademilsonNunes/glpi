-- ══════════════════════════════════════════════════════════
-- Q6 · FIRST RESPONSE TIME: TEMPO ATÉ 1º CONTATO DO TÉCNICO
-- Complementa o MTTR: mede a percepção do usuário
-- sobre agilidade de atendimento
-- ══════════════════════════════════════════════════════════
SELECT
    t.id                                           AS ticket_id,
    t.name                                         AS titulo,
    t.date                                         AS data_abertura,
    CONCAT(ut.firstname, ' ', ut.realname)         AS tecnico,
    -- Primeiro followup do técnico (não do usuário)
    MIN(f.date)                                    AS primeiro_followup_tecnico,
    TIMESTAMPDIFF(MINUTE, t.date, MIN(f.date))     AS min_ate_primeiro_contato,
    ROUND(TIMESTAMPDIFF(MINUTE, t.date,
          MIN(f.date)) / 60.0, 2)                 AS hrs_ate_primeiro_contato,
    CASE WHEN TIMESTAMPDIFF(MINUTE, t.date,
              MIN(f.date)) <= 60
         THEN 1 ELSE 0
    END                                            AS respondeu_em_1h,
    CASE t.priority
        WHEN 4 THEN 'Alta'
        WHEN 5 THEN 'Muito Alta'
        ELSE 'Outra'
    END                                            AS prioridade
FROM glpi_tickets t
-- Técnico atribuído
JOIN glpi_tickets_users tut
    ON tut.tickets_id = t.id AND tut.type = 2
JOIN glpi_users ut
    ON ut.id = tut.users_id
-- Apenas followups do técnico (não do requerente)
JOIN glpi_itilfollowups f
    ON f.items_id = t.id
   AND f.itemtype = 'Ticket'
   AND f.users_id = ut.id
   AND f.is_private = 0
WHERE t.is_deleted = 0
  AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
GROUP BY t.id, ut.id
ORDER BY min_ate_primeiro_contato DESC;


