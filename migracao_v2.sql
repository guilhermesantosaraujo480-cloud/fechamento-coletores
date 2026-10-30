-- =====================================================================
-- MIGRAÇÃO V2 - rode no Supabase: SQL Editor > New query > Run
-- (pode rodar mais de uma vez; não apaga nada)
-- =====================================================================

-- Trilha de auditoria (quem aprovou, pagou, excluiu, criou usuário...)
create table if not exists auditoria (
  id         bigint generated always as identity primary key,
  usuario    text,
  acao       text,
  detalhe    text,
  data_hora  timestamptz not null default now()
);
create index if not exists idx_auditoria_data on auditoria (data_hora desc);

-- Permite desativar usuários sem apagar o histórico
alter table usuarios add column if not exists ativo boolean not null default true;

-- Índices: deixam os filtros por período e status rápidos quando o volume cresce
create index if not exists idx_coletas_data         on coletas (data);
create index if not exists idx_coletas_status       on coletas (status);
create index if not exists idx_coletas_coletor_data on coletas (coletor, data);
create index if not exists idx_vales_data           on vales_coleta (data);
create index if not exists idx_premiacoes_data      on premiacoes (data);
create index if not exists idx_usuarios_token       on usuarios (session_token);

-- Se você já ativou o RLS (PASSO 3 do migracao.sql), proteja também a nova tabela:
-- alter table auditoria enable row level security;
