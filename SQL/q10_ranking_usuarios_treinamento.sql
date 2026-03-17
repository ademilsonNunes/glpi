-- ══════════════════════════════════════════════════════════
-- Q10 · RANKING DE USUÁRIOS: NECESSIDADE DE TREINAMENTO
-- ══════════════════════════════════════════════════════════
WITH base AS (
    SELECT
        u.id                                       AS user_id,
        CONCAT(u.firstname,' ',u.realname)         AS usuario,
        COALESCE(loc.completename,'N/I')           AS departamento,
        t.id                                       AS ticket_id,
        t.name                                     AS titulo,
        t.content                                  AS descricao,
        t.itilcategories_id                        AS cat_id,
        COALESCE(cat.completename,'N/I')           AS categoria,
        t.date                                     AS data_abertura
    FROM glpi_tickets t
    JOIN glpi_tickets_users tu
        ON tu.tickets_id = t.id AND tu.type = 1
    JOIN glpi_users u ON u.id = tu.users_id
    LEFT JOIN glpi_locations loc ON loc.id = t.locations_id
    LEFT JOIN glpi_itilcategories cat ON cat.id = t.itilcategories_id
    WHERE t.is_deleted = 0
      AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
),
reincidencia AS (
    SELECT a.user_id,
           COUNT(*) AS qtd_reincidencias
    FROM base a
    JOIN base b ON b.user_id = a.user_id
               AND b.cat_id  = a.cat_id
               AND b.ticket_id > a.ticket_id
               AND DATEDIFF(b.data_abertura, a.data_abertura) <= 30
    GROUP BY a.user_id
),
top_cat AS (
    SELECT user_id,
           categoria,
           ROW_NUMBER() OVER (
               PARTITION BY user_id
               ORDER BY COUNT(*) DESC
           ) AS rn
    FROM base
    GROUP BY user_id, categoria
)
SELECT
    b.usuario,
    b.departamento,
    COUNT(b.ticket_id)                             AS total_chamados,
    ROUND(100.0 * SUM(
        CASE WHEN CHAR_LENGTH(TRIM(b.titulo)) < 20
             THEN 1 ELSE 0 END
    ) / COUNT(b.ticket_id), 1)                     AS pct_titulo_ruim,
    ROUND(100.0 * SUM(
        CASE WHEN CHAR_LENGTH(TRIM(COALESCE(b.descricao,''))) < 30
             THEN 1 ELSE 0 END
    ) / COUNT(b.ticket_id), 1)                     AS pct_sem_descricao,
    ROUND(100.0 * SUM(
        CASE WHEN b.titulo = UPPER(b.titulo)
              AND CHAR_LENGTH(b.titulo) > 5
             THEN 1 ELSE 0 END
    ) / COUNT(b.ticket_id), 1)                     AS pct_caps_lock,
    COALESCE(r.qtd_reincidencias, 0)               AS qtd_reincidencias,
    ANY_VALUE(tc.categoria)                        AS top_categoria,   -- ← fix aplicado aqui
    LEAST(10, ROUND(
        (SUM(CASE WHEN CHAR_LENGTH(TRIM(b.titulo)) < 20
                  THEN 1 ELSE 0 END) / COUNT(b.ticket_id) * 3)
      + (SUM(CASE WHEN CHAR_LENGTH(TRIM(COALESCE(b.descricao,''))) < 30
                  THEN 1 ELSE 0 END) / COUNT(b.ticket_id) * 4)
      + (COALESCE(r.qtd_reincidencias, 0) * 0.5)
    , 2))                                          AS score_treinamento
FROM base b
LEFT JOIN reincidencia r ON r.user_id = b.user_id
LEFT JOIN top_cat tc     ON tc.user_id = b.user_id AND tc.rn = 1
GROUP BY
    b.user_id,
    b.usuario,
    b.departamento
HAVING total_chamados >= 1
ORDER BY score_treinamento DESC, total_chamados DESC
LIMIT 50;


