-- =====================================================================
-- MIGRAÇÃO - rode no Supabase: SQL Editor > New query > Run
-- =====================================================================

-- ---------- PASSO 1: tabelas novas (pode rodar agora, não quebra nada) ----------

-- Histórico de cada e-mail enviado (evita reenvio, controla limite diário por conta)
create table if not exists envios_email (
  id         bigint generated always as identity primary key,
  envio_id   text,
  protocolo  text,
  email      text,
  nome       text,
  conta      text,
  modelo     text,
  status     text,          -- 'enviado' ou 'erro'
  erro       text,
  data_hora  timestamptz not null default now()
);
create index if not exists idx_envios_status_data on envios_email (status, data_hora);
create index if not exists idx_envios_protocolo_email on envios_email (protocolo, email);

-- Quem pediu para não receber mais e-mails (responderam SAIR)
create table if not exists descadastros (
  email      text primary key,
  motivo     text,
  data_hora  timestamptz not null default now()
);

-- Modelos de e-mail salvos (escritos por você ou gerados pela IA e aprovados)
create table if not exists modelos_email (
  id           bigint generated always as identity primary key,
  nome         text not null,
  assunto      text not null,
  texto        text not null,
  regras       text,
  texto_whats  text,
  ativo        boolean not null default true,
  criado_em    timestamptz not null default now()
);

-- A coluna session_token passa a guardar o HASH do token (não o token em si).
-- Todo mundo precisará fazer login uma vez após a atualização do app.
update usuarios set session_token = null;

-- As senhas antigas (texto puro) são trocadas por hash automaticamente
-- no primeiro login de cada usuário. Nada a fazer aqui.


-- ---------- PASSO 2: bucket de comprovantes privado ----------
-- Rode SÓ DEPOIS de publicar o app.py novo (ele já gera links temporários,
-- inclusive para as fotos antigas).
--
-- update storage.buckets set public = false where id = 'comprovantes';


-- ---------- PASSO 3: fechar o acesso público às tabelas (RLS) ----------
-- Rode SÓ DEPOIS de trocar SUPABASE_KEY nos secrets do Streamlit pela chave
-- "service_role" (Project Settings > API). Essa chave fica apenas no servidor
-- do Streamlit e ignora o RLS. Com RLS ligado e sem políticas, a chave "anon"
-- (pública) deixa de enxergar qualquer dado.
--
-- alter table usuarios             enable row level security;
-- alter table coletas              enable row level security;
-- alter table vales_coleta         enable row level security;
-- alter table premiacoes           enable row level security;
-- alter table comprovantes_clientes enable row level security;
-- alter table logs_comprovantes    enable row level security;
-- alter table contas_email         enable row level security;
-- alter table cliques_email        enable row level security;
-- alter table envios_email         enable row level security;
-- alter table descadastros         enable row level security;
-- alter table modelos_email        enable row level security;
--
-- ATENÇÃO: a Edge Function "super-function" (contador de cliques) também precisa
-- usar a service_role (variável SUPABASE_SERVICE_ROLE_KEY, já disponível dentro
-- das Edge Functions) para continuar gravando em cliques_email.
