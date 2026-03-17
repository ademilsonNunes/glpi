-- ══════════════════════════════════════════════════════════
-- Q2 · REINCIDÊNCIA: MESMO USUÁRIO + MESMA CATEGORIA ≤ 30d
-- Indicador direto de necessidade de treinamento
-- ══════════════════════════════════════════════════════════
SELECT
    CONCAT(u.firstname, ' ', u.realname)   AS requerente,
    u.id                                   AS user_id,
    COALESCE(cat.completename,
             'Sem categoria')              AS categoria,
    COUNT(t.id)                            AS qtd_chamados,
    MIN(t.date)                            AS primeiro_chamado,
    MAX(t.date)                            AS ultimo_chamado,
    DATEDIFF(MAX(t.date), MIN(t.date))     AS intervalo_dias,
    GROUP_CONCAT(t.id ORDER BY t.date
                 SEPARATOR ', ')           AS ids_chamados,
    GROUP_CONCAT(t.name ORDER BY t.date
                 SEPARATOR ' | ')          AS titulos
FROM glpi_tickets t
JOIN glpi_tickets_users tu
    ON tu.tickets_id = t.id AND tu.type = 1
JOIN glpi_users u
    ON u.id = tu.users_id
LEFT JOIN glpi_itilcategories cat
    ON cat.id = t.itilcategories_id
WHERE t.is_deleted = 0
  AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
GROUP BY
    u.id,
    t.itilcategories_id
HAVING
    qtd_chamados >= 2              -- ao menos 2 chamados iguais
    AND intervalo_dias <= 30       -- dentro de 30 dias
ORDER BY
    qtd_chamados DESC,
    intervalo_dias ASC;
