-- =====================================================================
-- MIGRAÇÃO V3 (aba Rotas) - Supabase: SQL Editor > New query > Run
-- =====================================================================

-- Coletores que aparecem nas rotas (podem ou não ter login no sistema)
create table if not exists rota_coletores (
  id          bigint generated always as identity primary key,
  nome_rota   text not null unique,      -- como aparece nas pastas/planilhas (ex.: GEOVAN)
  usuario_id  bigint,                    -- vínculo opcional com usuarios.id
  telefone    text,                      -- WhatsApp individual (opcional)
  ativo       boolean not null default true,
  criado_em   timestamptz not null default now()
);

-- Grupos (ou números) de WhatsApp que recebem as rotas de cada empresa
create table if not exists rota_grupos (
  id       bigint generated always as identity primary key,
  empresa  text not null,
  nome     text,
  destino  text not null,                -- id do grupo (ex.: 1203630000000000@g.us) ou número com DDI
  ativo    boolean not null default true
);

-- Empresas criadas pela tela (Reintegra e TIM já vêm prontas no código)
create table if not exists rota_perfis (
  id         bigint generated always as identity primary key,
  nome       text not null unique,
  definicao  jsonb not null
);

-- Histórico de envios
create table if not exists rota_envios (
  id         bigint generated always as identity primary key,
  data_hora  timestamptz not null default now(),
  data_rota  date,
  empresa    text,
  coletor    text,
  qtd        int,
  destino    text,
  status     text,
  detalhe    text,
  usuario    text
);
create index if not exists idx_rota_envios_dia on rota_envios (empresa, data_rota, status);

-- Coletores que já existiam nos seus scripts
insert into rota_coletores (nome_rota) values
  ('GEOVAN'), ('RAFAEL'), ('GABRIEL'), ('RENILTON'), ('ARLEIDE.JULIENE'), ('GUILHERME'),
  ('CARLOS'), ('DANILO'), ('CARLOS.ALBERTO'), ('JOSENILDA'), ('OUTROS')
on conflict (nome_rota) do nothing;

-- Se você usa RLS (migracao.sql, PASSO 3), proteja também:
-- alter table rota_coletores enable row level security;
-- alter table rota_grupos    enable row level security;
-- alter table rota_perfis    enable row level security;
-- alter table rota_envios    enable row level security;
