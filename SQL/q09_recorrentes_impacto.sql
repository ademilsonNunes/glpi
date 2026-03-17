SELECT
    tr.name                                        AS nome_recorrente,
    tr.is_active                                   AS ativo,          -- campo correto no GLPI
    ROUND(tr.periodicity / 86400, 0)               AS periodicidade_dias,
    tr.begin_date                                   AS data_inicio,
    COUNT(t.id)                                    AS qtd_gerados_90d,
    ROUND(COUNT(t.id) * (365.0 / 90), 0)          AS projecao_anual,
    ROUND(SUM(
        TIMESTAMPDIFF(MINUTE, t.date,
        COALESCE(t.solvedate, t.closedate)) / 60.0
    ), 1)                                          AS total_horas_corridas,
    ROUND(AVG(
        TIMESTAMPDIFF(MINUTE, t.date,
        COALESCE(t.solvedate, t.closedate)) / 60.0
    ), 2)                                          AS media_horas_por_chamado
FROM glpi_ticketrecurrents tr
LEFT JOIN glpi_tickets t
    ON t.name LIKE CONCAT('%', tr.name, '%')
   AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
   AND t.is_deleted = 0
GROUP BY
    tr.id,
    tr.name,
    tr.is_active,
    tr.periodicity,
    tr.begin_date
ORDER BY qtd_gerados_90d DESC;
