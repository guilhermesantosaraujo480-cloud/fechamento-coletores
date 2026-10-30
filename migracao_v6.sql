-- =====================================================================
-- MIGRAÇÃO V6 - DESEMPENHO - Supabase: SQL Editor > New query > Run  (pode rodar mais de uma vez)
--   1) Índices nas colunas mais consultadas (telas e consultas mais rápidas quando o histórico cresce)
--   2) Função opcional de limpeza de histórico antigo (só roda quando VOCÊ chamar)
-- Cada índice só é criado se a tabela/coluna existir: nada aqui quebra se alguma tabela ainda não foi criada.
-- =====================================================================

-- ---------------------------------------------------------------- 1) ÍNDICES
do $$
declare
  r record;
begin
  for r in
    select * from (values
      ('idx_coletas_data',            'coletas',               '(data)'),
      ('idx_coletas_coletor_data',    'coletas',               '(coletor, data)'),
      ('idx_coletas_status',          'coletas',               '(status)'),
      ('idx_vales_coletor_data',      'vales_coleta',          '(coletor, data)'),
      ('idx_premiacoes_coletor_data', 'premiacoes',            '(coletor, data)'),
      ('idx_usuarios_usuario',        'usuarios',              '(usuario)'),
      ('idx_auditoria_data',          'auditoria',             '(data_hora desc)'),
      ('idx_logs_comprov_data',       'logs_comprovantes',     '(data_hora desc)'),
      ('idx_comprov_os',              'comprovantes_clientes', '(ordem_servico)'),
      ('idx_comprov_emissao',         'comprovantes_clientes', '(data_emissao desc)'),
      ('idx_envios_status_data',      'envios_email',          '(status, data_hora)'),
      ('idx_envios_protocolo_email',  'envios_email',          '(protocolo, email)'),
      ('idx_envios_envio_id',         'envios_email',          '(envio_id)'),
      ('idx_cliques_envio_id',        'cliques_email',         '(envio_id)'),
      ('idx_descadastros_email',      'descadastros',          '(email)'),
      ('idx_rota_envios_data',        'rota_envios',           '(id desc)'),
      ('idx_bipagem_itens_os',        'bipagem_itens',         '(os)')
    ) as t(nome, tabela, colunas)
  loop
    begin
      execute format('create index if not exists %I on %I %s', r.nome, r.tabela, r.colunas);
    exception when undefined_table or undefined_column then
      raise notice 'ignorado (tabela/coluna não existe): % em %', r.nome, r.tabela;
    end;
  end loop;
end $$;

-- ---------------------------------------------------------------- 2) LIMPEZA OPCIONAL
-- Apaga só o que é "rascunho técnico" antigo. NUNCA apaga: coletas, vales, premiações, usuários, envios_email
-- (o histórico de e-mails enviados evita reenvio) nem descadastros.
--   select limpar_historico_antigo();          -- usa os prazos padrão (abaixo)
--   select limpar_historico_antigo(90, 365);   -- itens de fila/rota com mais de 90 dias; auditoria com mais de 365
create or replace function limpar_historico_antigo(dias_tecnico int default 120, dias_auditoria int default 365)
returns text
language plpgsql
as $$
declare
  n bigint;
  resumo text := '';
begin
  -- destinos de campanhas de e-mail já concluídas/canceladas (os totais da campanha continuam guardados)
  if to_regclass('campanha_destinos') is not null and to_regclass('campanhas') is not null then
    delete from campanha_destinos d using campanhas c
     where d.campanha_id = c.id and c.status in ('concluida', 'cancelada')
       and coalesce(c.finalizado_em, c.criado_em) < now() - make_interval(days => dias_tecnico);
    get diagnostics n = row_count;
    resumo := resumo || format('destinos de campanha: %s; ', n);
  end if;
  -- itens de bipagem de lotes terminados
  if to_regclass('bipagem_itens') is not null and to_regclass('bipagem_lotes') is not null then
    delete from bipagem_itens i using bipagem_lotes l
     where i.lote_id = l.id and l.status in ('concluido', 'cancelado', 'parado', 'erro')
       and coalesce(l.finalizado_em, l.criado_em) < now() - make_interval(days => dias_tecnico);
    get diagnostics n = row_count;
    resumo := resumo || format('itens de bipagem: %s; ', n);
  end if;
  -- fotografias diárias das rotas
  if to_regclass('rota_snapshots') is not null then
    delete from rota_snapshots where data < current_date - dias_tecnico;
    get diagnostics n = row_count;
    resumo := resumo || format('fotografias de rota: %s; ', n);
  end if;
  -- auditoria e buscas de comprovantes antigas
  if to_regclass('auditoria') is not null then
    delete from auditoria where data_hora < now() - make_interval(days => dias_auditoria);
    get diagnostics n = row_count;
    resumo := resumo || format('auditoria: %s; ', n);
  end if;
  if to_regclass('logs_comprovantes') is not null then
    delete from logs_comprovantes where data_hora < now() - make_interval(days => dias_auditoria);
    get diagnostics n = row_count;
    resumo := resumo || format('buscas de comprovante: %s; ', n);
  end if;
  return coalesce(nullif(resumo, ''), 'nada para limpar');
end;
$$;
