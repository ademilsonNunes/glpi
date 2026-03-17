SELECT
    CASE DAYOFWEEK(t.date)
        WHEN 1 THEN '1-Domingo'
        WHEN 2 THEN '2-Segunda'
        WHEN 3 THEN '3-Terca'
        WHEN 4 THEN '4-Quarta'
        WHEN 5 THEN '5-Quinta'
        WHEN 6 THEN '6-Sexta'
        WHEN 7 THEN '7-Sabado'
    END                                            AS dia_semana,
    DAYOFWEEK(t.date)                              AS dia_num,
    HOUR(t.date)                                   AS hora_abertura,
    COUNT(t.id)                                    AS total_chamados,
    SUM(CASE WHEN t.priority >= 4 THEN 1 ELSE 0 END)
                                                   AS alta_prioridade,
    ROUND(100.0 * SUM(
        CASE WHEN t.priority >= 4 THEN 1 ELSE 0 END)
    / COUNT(t.id), 1)                              AS pct_alta_prioridade
FROM glpi_tickets t
WHERE t.is_deleted = 0
  AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
GROUP BY
    DAYOFWEEK(t.date),                             -- ← já existia
    HOUR(t.date),                                  -- ← já existia
    CASE DAYOFWEEK(t.date)                         -- ← adicionado
        WHEN 1 THEN '1-Domingo'
        WHEN 2 THEN '2-Segunda'
        WHEN 3 THEN '3-Terca'
        WHEN 4 THEN '4-Quarta'
        WHEN 5 THEN '5-Quinta'
        WHEN 6 THEN '6-Sexta'
        WHEN 7 THEN '7-Sabado'
    END
ORDER BY
    dia_num,
    hora_abertura;


