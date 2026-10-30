-- =====================================================================
-- MIGRAÇÃO V5 - Supabase: SQL Editor > New query > Run  (pode rodar mais de uma vez)
--   1) Aparelhos acrescentados na aprovação da coleta (só o administrador vê)
--   2) Bipagem: lotes, itens e batimento do agente local
-- =====================================================================

-- ---------------------------------------------------------------- 1) COLETAS
alter table coletas add column if not exists qtd_acrescimo int not null default 0;

-- ---------------------------------------------------------------- 2) BIPAGEM
create table if not exists bipagem_lotes (
  id             bigint generated always as identity primary key,
  criado_em      timestamptz not null default now(),
  criado_por     text,
  nome           text,
  status         text not null default 'pendente',   -- pendente | executando | parando | parado | concluido | erro | cancelado
  seriais        jsonb not null default '[]'::jsonb, -- lista de seriais do pool
  qtd_aparelhos  int not null default 1,             -- 1 ou 2 aparelhos por OS
  equip1         text,
  equip2         text,
  limite_ordens  int not null default 1,
  indice_pool    int not null default 0,             -- até onde do pool já foi usado
  ordens_ok      int not null default 0,
  ordens_erro    int not null default 0,
  parar          boolean not null default false,
  mensagem       text default '',
  agente         text,
  iniciado_em    timestamptz,
  finalizado_em  timestamptz
);
create index if not exists idx_bipagem_lotes_status on bipagem_lotes (status, id);

create table if not exists bipagem_itens (
  id         bigint generated always as identity primary key,
  lote_id    bigint not null references bipagem_lotes(id) on delete cascade,
  os         text,
  status     text,                                   -- ok | erro | verificar ...
  serial1    text default '',
  serial2    text default '',
  tentativas int not null default 0,
  obs        text default '',
  criado_em  timestamptz not null default now()
);
create index if not exists idx_bipagem_itens_lote on bipagem_itens (lote_id, id);

create table if not exists bipagem_agente (
  nome         text primary key,
  ultimo_sinal timestamptz,
  info         text
);

-- Se você usa RLS nas outras tabelas e o app usa a chave service_role, não precisa de mais nada.
-- (Para travar também o acesso público, descomente:)
-- alter table bipagem_lotes  enable row level security;
-- alter table bipagem_itens  enable row level security;
-- alter table bipagem_agente enable row level security;
