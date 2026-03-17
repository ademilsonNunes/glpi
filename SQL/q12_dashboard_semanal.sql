SELECT
    CONCAT(
        YEAR(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)),
        '-W',
        LPAD(WEEK(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), 3), 2, '0')
    ) AS semana_ref,
    DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY) AS data_inicio,
    DATE_ADD(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), INTERVAL 6 DAY) AS data_fim,
    SUM(
        CASE
            WHEN t.date BETWEEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
                           AND DATE_ADD(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), INTERVAL 6 DAY)
            THEN 1 ELSE 0
        END
    ) AS total_abertos,
    SUM(
        CASE
            WHEN COALESCE(t.solvedate, t.closedate)
                 BETWEEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
                     AND DATE_ADD(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), INTERVAL 6 DAY)
            THEN 1 ELSE 0
        END
    ) AS total_fechados,
    SUM(
        CASE
            WHEN COALESCE(t.solvedate, t.closedate)
                 BETWEEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
                     AND DATE_ADD(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), INTERVAL 6 DAY)
             AND (
                 t.time_to_resolve IS NULL
                 OR COALESCE(t.solvedate, t.closedate) <= t.time_to_resolve
             )
            THEN 1 ELSE 0
        END
    ) AS sla_dentro,
    SUM(
        CASE
            WHEN COALESCE(t.solvedate, t.closedate)
                 BETWEEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
                     AND DATE_ADD(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), INTERVAL 6 DAY)
             AND t.time_to_resolve IS NOT NULL
             AND COALESCE(t.solvedate, t.closedate) > t.time_to_resolve
            THEN 1 ELSE 0
        END
    ) AS sla_violado,
    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN COALESCE(t.solvedate, t.closedate)
                     BETWEEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
                         AND DATE_ADD(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), INTERVAL 6 DAY)
                 AND (
                     t.time_to_resolve IS NULL
                     OR COALESCE(t.solvedate, t.closedate) <= t.time_to_resolve
                 )
                THEN 1 ELSE 0
            END
        ) /
        NULLIF(
            SUM(
                CASE
                    WHEN COALESCE(t.solvedate, t.closedate)
                         BETWEEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
                             AND DATE_ADD(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), INTERVAL 6 DAY)
                    THEN 1 ELSE 0
                END
            ),
            0
        ),
        1
    ) AS pct_compliance,
    SUM(CASE WHEN t.status NOT IN (5, 6) THEN 1 ELSE 0 END) AS backlog_atual
FROM glpi_tickets t
WHERE t.is_deleted = 0;
