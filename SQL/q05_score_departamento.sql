-- ══════════════════════════════════════════════════════════
-- Q5 · SCORE DE COMUNICAÇÃO POR DEPARTAMENTO
-- Saída gerencial: ranking de áreas que mais precisam
-- de treinamento no uso do portal de chamados
-- ══════════════════════════════════════════════════════════
SELECT
    COALESCE(loc.completename, 'Não informado')   AS departamento,
    COUNT(t.id)                                   AS total_chamados,
    -- % título curto (< 20 chars)
    ROUND(100.0 * SUM(
        CASE WHEN CHAR_LENGTH(TRIM(t.name)) < 20
             THEN 1 ELSE 0 END
    ) / COUNT(t.id), 1)                           AS pct_titulo_ruim,
    -- % sem descrição ou descrição vazia
    ROUND(100.0 * SUM(
        CASE WHEN CHAR_LENGTH(TRIM(COALESCE(t.content,''))) < 20
             THEN 1 ELSE 0 END
    ) / COUNT(t.id), 1)                           AS pct_sem_descricao,
    -- % título em caps lock
    ROUND(100.0 * SUM(
        CASE WHEN t.name = UPPER(t.name)
              AND CHAR_LENGTH(t.name) > 5
             THEN 1 ELSE 0 END
    ) / COUNT(t.id), 1)                           AS pct_caps_lock,
    -- % sem número de referência na descrição
    ROUND(100.0 * SUM(
        CASE WHEN NOT COALESCE(t.content,'') REGEXP '[0-9]{5,}'
             THEN 1 ELSE 0 END
    ) / COUNT(t.id), 1)                           AS pct_sem_numero_ref,
    -- Média de caracteres na descrição
    ROUND(AVG(
        CHAR_LENGTH(TRIM(COALESCE(t.content,''))))
    , 0)                                          AS media_chars_descricao,
    -- Score de comunicação: penaliza cada indicador ruim (0=ruim, 10=ótimo)
    ROUND(10.0
        - (SUM(CASE WHEN CHAR_LENGTH(TRIM(t.name)) < 20 THEN 1 ELSE 0 END)
           / COUNT(t.id) * 3.0)
        - (SUM(CASE WHEN CHAR_LENGTH(TRIM(COALESCE(t.content,''))) < 20
                    THEN 1 ELSE 0 END)
           / COUNT(t.id) * 4.0)
        - (SUM(CASE WHEN t.name = UPPER(t.name)
                         AND CHAR_LENGTH(t.name) > 5
                    THEN 1 ELSE 0 END)
           / COUNT(t.id) * 1.0)
        - (SUM(CASE WHEN NOT COALESCE(t.content,'') REGEXP '[0-9]{5,}'
                    THEN 1 ELSE 0 END)
           / COUNT(t.id) * 2.0)
    , 2)                                          AS score_comunicacao
FROM glpi_tickets t
JOIN glpi_tickets_users tu
    ON tu.tickets_id = t.id AND tu.type = 1
LEFT JOIN glpi_locations loc
    ON loc.id = t.locations_id
WHERE t.is_deleted = 0
  AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
GROUP BY loc.id, loc.completename
HAVING total_chamados >= 1
ORDER BY score_comunicacao ASC;   -- pior primeiro


