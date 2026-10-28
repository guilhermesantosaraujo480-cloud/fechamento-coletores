-- =====================================================================
-- MIGRAÇÃO V7 - Supabase: SQL Editor > New query > Run  (pode rodar mais de uma vez; nada é apagado)
--   1) SMS pelo celular (gateway): celulares, campanhas, destinos, histórico e lista de "SAIR"
--   2) Agendamento de campanhas de e-mail ("Começar em")
--   3) "Já chamado" na lista de quem clicou
--   4) Mensagens prontas do WhatsApp das rotas
-- =====================================================================

-- ---------------------------------------------------------------- 1) SMS
create table if not exists sms_gateways (
  id            bigint generated always as identity primary key,
  nome          text not null,                      -- ex.: "Chip Vivo 1"
  url_base      text not null default 'https://api.sms-gate.app',
  usuario       text not null,
  senha         text not null,                      -- protegida pela CHAVE_CRIPTO (nunca em texto puro se a chave existir)
  sim_numero    int,                                -- 1 ou 2 (aparelho com dois chips); vazio = padrão do app
  limite_diario int not null default 100,
  ativo         boolean not null default true,
  criado_em     timestamptz not null default now()
);

create table if not exists sms_campanhas (
  id               bigint generated always as identity primary key,
  nome             text not null,
  status           text not null default 'pendente',   -- pendente | rodando | pausada | concluida | cancelada
  criado_por       text,
  criado_em        timestamptz not null default now(),
  iniciado_em      timestamptz,
  finalizado_em    timestamptz,
  atualizado_em    timestamptz,
  agendada_para    timestamptz,                        -- só começa depois desta hora
  lease_ate        timestamptz,
  textos           jsonb not null,                     -- lista de textos (modelos) da campanha
  ctx              jsonb not null,                     -- empresa, número do WhatsApp...
  delay_min        numeric not null default 20,
  delay_max        numeric not null default 45,
  janela_ini       int,                                -- hora inicial permitida (ex.: 9)
  janela_fim       int,                                -- hora final (ex.: 19)
  domingo          boolean not null default false,     -- enviar também aos domingos?
  sem_acentos      boolean not null default true,
  permitir_reenvio boolean not null default false,
  total            int not null default 0,
  enviados         int not null default 0,
  erros            int not null default 0,
  ignorados        int not null default 0,
  motivo           text,
  aviso            text
);
create index if not exists idx_sms_campanhas_status on sms_campanhas (status, id);

create table if not exists sms_destinos (
  id            bigint generated always as identity primary key,
  campanha_id   bigint not null references sms_campanhas(id) on delete cascade,
  ordem         int not null,
  protocolo     text,
  nome          text,
  telefone      text,                                  -- +55DDDNÚMERO (vazio = sem celular válido)
  email         text,
  dados         jsonb not null default '{}'::jsonb,    -- inclui _texto (posição do texto sorteado)
  status        text not null default 'pendente',      -- pendente | enviando | enviado | erro | ignorado
  detalhe       text,
  gateway_id    bigint,                                -- celular que enviou
  msg_id        text,                                  -- id da mensagem no aplicativo
  processado_em timestamptz
);
create index if not exists idx_sms_destinos_fila on sms_destinos (campanha_id, status, ordem);

create table if not exists sms_envios (
  id            bigint generated always as identity primary key,
  campanha_id   bigint,
  protocolo     text,
  telefone      text,
  nome          text,
  texto         text,
  modelo        text,
  gateway_id    bigint,
  gateway_nome  text,
  status        text not null,                          -- enviado | erro
  erro          text,
  msg_id        text,
  data_hora     timestamptz not null default now()
);
alter table sms_envios add column if not exists estado text;   -- Delivered | Failed | Sent | Pending (conferido no app do celular)
create index if not exists idx_sms_envios_data on sms_envios (data_hora);
create index if not exists idx_sms_envios_protocolo on sms_envios (protocolo, telefone);

create table if not exists sms_descadastros (
  telefone   text primary key,                          -- só dígitos, com 55
  motivo     text,
  data_hora  timestamptz not null default now()
);

-- ---------------------------------------------------------------- 2) AGENDAMENTO DE E-MAIL
alter table campanhas add column if not exists agendada_para timestamptz;

-- ---------------------------------------------------------------- 3) JÁ CHAMADO (quem clicou)
create table if not exists cliques_chamados (
  protocolo  text not null,
  email      text not null default '',
  canal      text not null default 'whatsapp',          -- whatsapp | sms
  por        text,
  data_hora  timestamptz not null default now(),
  primary key (protocolo, email)
);

-- ---------------------------------------------------------------- 4) MENSAGENS PRONTAS (WhatsApp das rotas)
create table if not exists mensagens_rota (
  id         bigint generated always as identity primary key,
  nome       text not null,
  texto      text not null,
  criado_em  timestamptz not null default now()
);

-- Se você usa RLS (migracao.sql, PASSO 3), proteja também (o trabalhador usa a service_role e ignora RLS):
-- alter table sms_gateways      enable row level security;
-- alter table sms_campanhas     enable row level security;
-- alter table sms_destinos      enable row level security;
-- alter table sms_envios        enable row level security;
-- alter table sms_descadastros  enable row level security;
-- alter table cliques_chamados  enable row level security;
-- alter table mensagens_rota    enable row level security;
