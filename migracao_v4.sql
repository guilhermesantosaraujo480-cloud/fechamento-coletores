-- =====================================================================
-- MIGRAÇÃO V4 - Supabase: SQL Editor > New query > Run  (pode rodar mais de uma vez)
--   1) Disparo de e-mails em segundo plano (fila)
--   2) Rotas: tipo de coletor, apelidos e fotografia diária (acompanhamento)
-- =====================================================================

-- ---------------------------------------------------------------- 1) FILA DE DISPARO
create table if not exists campanhas (
  id               bigint generated always as identity primary key,
  nome             text not null,
  status           text not null default 'pendente',   -- pendente | rodando | pausada | concluida | cancelada
  criado_por       text,
  criado_em        timestamptz not null default now(),
  iniciado_em      timestamptz,
  finalizado_em    timestamptz,
  atualizado_em    timestamptz,
  lease_ate        timestamptz,                        -- "reserva": só um trabalhador por vez
  modelo_nome      text,
  modelo           jsonb not null,
  ctx              jsonb not null,
  delay_min        numeric not null default 4,
  delay_max        numeric not null default 8,
  permitir_reenvio boolean not null default false,
  total            int not null default 0,
  enviados         int not null default 0,
  erros            int not null default 0,
  ignorados        int not null default 0,
  falhas_log       int not null default 0,
  motivo           text,                               -- por que parou / aviso
  aviso            text
);
create index if not exists idx_campanhas_status on campanhas (status, id);

create table if not exists campanha_destinos (
  id           bigint generated always as identity primary key,
  campanha_id  bigint not null references campanhas(id) on delete cascade,
  ordem        int not null,
  protocolo    text,
  email        text,
  dados        jsonb not null,                         -- linha da planilha já padronizada
  status       text not null default 'pendente',       -- pendente | enviando | enviado | erro | ignorado
  detalhe      text,
  processado_em timestamptz
);
create index if not exists idx_destinos_fila on campanha_destinos (campanha_id, status, ordem);

-- ------------------------------------------------------------------ 2) ROTAS
alter table rota_coletores add column if not exists tipo text not null default 'normal';  -- normal | retentativa | deposito

create table if not exists rota_apelidos (
  apelido    text primary key,          -- nome como aparece no relatório, normalizado (MAIÚSCULAS, sem acento)
  nome_rota  text not null
);

create table if not exists rota_snapshots (
  id        bigint generated always as identity primary key,
  chave     text not null unique,       -- empresa|data|os_id
  empresa   text not null,
  data      date not null,
  os_id     text not null,
  coletor   text,
  bairro    text,
  cidade    text,
  motivo    text,
  urgente   boolean default false
);
create index if not exists idx_snap_empresa_data on rota_snapshots (empresa, data);

-- Se você usa RLS (migracao.sql, PASSO 3), proteja também (o trabalhador usa a service_role e ignora RLS):
-- alter table campanhas          enable row level security;
-- alter table campanha_destinos  enable row level security;
-- alter table rota_apelidos      enable row level security;
-- alter table rota_snapshots     enable row level security;
