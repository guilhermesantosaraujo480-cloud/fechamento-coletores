-- v12: "Esqueci a senha" (pedido ao administrador + senha temporária com troca obrigatória). Aditivo; pode rodar mais de uma vez.
alter table usuarios add column if not exists trocar_senha boolean not null default false;
create table if not exists pedidos_senha (
  id bigserial primary key,
  usuario text not null,
  criado_em timestamptz not null default now(),
  atendido boolean not null default false,
  atendido_por text,
  atendido_em timestamptz
);
create index if not exists idx_pedidos_senha_abertos on pedidos_senha (usuario) where not atendido;
alter table pedidos_senha enable row level security;  -- só a chave de serviço do sistema acessa
