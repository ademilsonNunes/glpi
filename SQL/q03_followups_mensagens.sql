-- ══════════════════════════════════════════════════════════
-- Q3 · FOLLOWUPS: TODAS AS MENSAGENS COM METADADOS
-- Extrai trocas de mensagem para análise de qualidade textual
-- Remova: AND f.is_private = 0  para incluir notas internas
-- ══════════════════════════════════════════════════════════
SELECT
    t.id                                         AS ticket_id,
    t.name                                       AS titulo_chamado,
    t.date                                       AS abertura_chamado,
    f.id                                         AS followup_id,
    f.date                                       AS data_followup,
    -- Minutos desde a abertura até este followup
    TIMESTAMPDIFF(MINUTE, t.date, f.date)        AS min_desde_abertura,
    CONCAT(u.firstname, ' ', u.realname)         AS autor,
    u.id                                         AS autor_id,
    -- Determina se o autor é o requerente ou técnico
    CASE
        WHEN EXISTS (
            SELECT 1 FROM glpi_tickets_users tu2
            WHERE tu2.tickets_id = t.id
              AND tu2.users_id   = f.users_id
              AND tu2.type       = 1
        ) THEN 'Requerente (Usuário)'
        ELSE 'Técnico / Suporte'
    END                                          AS tipo_autor,
    f.content                                    AS conteudo,
    -- Métricas de qualidade textual
    CHAR_LENGTH(TRIM(f.content))                 AS tamanho_chars,
    -- Estimativa de palavras (espaços + 1)
    CHAR_LENGTH(TRIM(f.content))
      - CHAR_LENGTH(REPLACE(TRIM(f.content),' ','')) + 1
                                                 AS qtd_palavras_estimada,
    -- Detecta se há número de NF, pedido ou romaneio
    CASE WHEN f.content REGEXP '[0-9]{5,}' THEN 1 ELSE 0
    END                                          AS contem_numero_referencia,
    -- Detecta prints/anexos mencionados
    CASE WHEN LOWER(f.content) REGEXP
        '(print|printscreen|anexo|imagem|screenshot|captura)' THEN 1 ELSE 0
    END                                          AS menciona_anexo,
    f.is_private                                 AS nota_interna,
    -- Canal de origem
    COALESCE(rt.name, 'Não informado')           AS canal_origem
FROM glpi_itilfollowups f
JOIN glpi_tickets t
    ON t.id = f.items_id AND f.itemtype = 'Ticket'
LEFT JOIN glpi_users u
    ON u.id = f.users_id
LEFT JOIN glpi_requesttypes rt
    ON rt.id = f.requesttypes_id
WHERE t.is_deleted = 0
  AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)

ORDER BY t.id, f.date;


