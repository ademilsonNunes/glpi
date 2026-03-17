-- ══════════════════════════════════════════════════════════
-- Q8 · PROBLEMAS ITIL + CHAMADOS VINCULADOS
-- Mostra quais Problemas formais têm mais incidentes
-- vinculados e qual o custo em horas acumulado
-- ══════════════════════════════════════════════════════════
SELECT
    p.id                                           AS problema_id,
    p.name                                         AS titulo_problema,
    CASE p.status
        WHEN 1 THEN 'Novo'
        WHEN 2 THEN 'Em análise'
        WHEN 3 THEN 'Resolvido'
        WHEN 4 THEN 'Fechado'
    END                                            AS status_problema,
    p.date                                         AS data_abertura_problema,
    CASE p.priority
        WHEN 1 THEN 'Muito Baixa'
        WHEN 2 THEN 'Baixa'
        WHEN 3 THEN 'Média'
        WHEN 4 THEN 'Alta'
        WHEN 5 THEN 'Muito Alta'
    END                                            AS prioridade,
    COALESCE(cat.completename, 'Sem categoria')    AS categoria,
    COUNT(pt.tickets_id)                           AS qtd_incidentes_vinculados,
    MIN(t.date)                                    AS primeiro_incidente,
    MAX(t.date)                                    AS ultimo_incidente,
    DATEDIFF(MAX(t.date), MIN(t.date))             AS dias_gerando_incidentes,
    -- Soma de tempo técnico gasto nos incidentes (horas corridas)
    ROUND(SUM(
        TIMESTAMPDIFF(MINUTE, t.date,
        COALESCE(t.solvedate, t.closedate)) / 60.0
    ), 1)                                          AS total_horas_incidentes,
    GROUP_CONCAT(pt.tickets_id ORDER BY t.date
                 SEPARATOR ', ')                   AS ids_chamados_vinculados
FROM glpi_problems p
LEFT JOIN glpi_problems_tickets pt
    ON pt.problems_id = p.id
LEFT JOIN glpi_tickets t
    ON t.id = pt.tickets_id
LEFT JOIN glpi_itilcategories cat
    ON cat.id = p.itilcategories_id
WHERE p.is_deleted = 0
GROUP BY p.id
ORDER BY qtd_incidentes_vinculados DESC, dias_gerando_incidentes DESC;