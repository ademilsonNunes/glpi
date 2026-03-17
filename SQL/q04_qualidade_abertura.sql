-- ══════════════════════════════════════════════════════════
-- Q4 · QUALIDADE DE ABERTURA: TÍTULOS E DESCRIÇÕES
-- Score individual por chamado para identificar usuários
-- que não preenchem adequadamente o portal
-- ══════════════════════════════════════════════════════════
SELECT
    t.id                                           AS ticket_id,
    t.date                                         AS data_abertura,
    CONCAT(u.firstname, ' ', u.realname)           AS autor,
    COALESCE(loc.completename, 'N/I')              AS departamento,
    COALESCE(cat.completename, 'Sem categoria')    AS categoria,
    t.name                                         AS titulo,
    CHAR_LENGTH(TRIM(t.name))                      AS chars_titulo,
    CHAR_LENGTH(TRIM(COALESCE(t.content,'')))      AS chars_descricao,
    -- Score qualidade do título
    CASE
        WHEN CHAR_LENGTH(TRIM(t.name)) < 10
            THEN 'Ruim (< 10 chars)'
        WHEN CHAR_LENGTH(TRIM(t.name)) BETWEEN 10 AND 25
            THEN 'Regular (10-25 chars)'
        ELSE 'Bom (> 25 chars)'
    END                                            AS qualidade_titulo,
    -- Score qualidade da descrição
    CASE
        WHEN CHAR_LENGTH(TRIM(COALESCE(t.content,''))) = 0
            THEN 'Vazio (sem descrição)'
        WHEN CHAR_LENGTH(TRIM(COALESCE(t.content,''))) < 50
            THEN 'Ruim (< 50 chars)'
        WHEN CHAR_LENGTH(TRIM(COALESCE(t.content,''))) BETWEEN 50 AND 150
            THEN 'Regular (50-150 chars)'
        ELSE 'Bom (> 150 chars)'
    END                                            AS qualidade_descricao,
    -- Título todo em maiúsculas = urgência falsa / hábito ruim
    CASE WHEN t.name = UPPER(t.name)
         AND CHAR_LENGTH(t.name) > 5
         THEN 1 ELSE 0
    END                                            AS titulo_em_caps_lock,
    -- Contém número de referência (NF, pedido, romaneio)
    CASE WHEN COALESCE(t.content,'') REGEXP '[0-9]{5,}'
         THEN 1 ELSE 0
    END                                            AS tem_numero_referencia,
    -- Prioridade selecionada pelo usuário
    CASE t.priority
        WHEN 1 THEN 'Muito Baixa'
        WHEN 2 THEN 'Baixa'
        WHEN 3 THEN 'Média'
        WHEN 4 THEN 'Alta'
        WHEN 5 THEN 'Muito Alta'
    END                                            AS prioridade_selecionada,
    -- Quantidade de interações posteriores (proxy de retrabalho por falta de info)
    (SELECT COUNT(*) FROM glpi_itilfollowups f
     WHERE f.items_id = t.id
       AND f.itemtype = 'Ticket'
       AND f.is_private = 0
    )                                              AS qtd_trocas_mensagens
FROM glpi_tickets t
JOIN glpi_tickets_users tu
    ON tu.tickets_id = t.id AND tu.type = 1
JOIN glpi_users u
    ON u.id = tu.users_id
LEFT JOIN glpi_itilcategories cat
    ON cat.id = t.itilcategories_id
LEFT JOIN glpi_locations loc
    ON loc.id = t.locations_id
WHERE t.is_deleted = 0
  AND t.date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
ORDER BY chars_descricao ASC, t.date DESC;


