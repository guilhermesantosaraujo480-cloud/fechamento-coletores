-- v10: categorias de serviço/premiação (aditivo, pode rodar mais de uma vez)
alter table premiacoes add column if not exists categoria text;

create table if not exists categorias_servico (
  nome  text primary key,
  ativo boolean not null default true
);
alter table categorias_servico enable row level security;  -- só a chave de serviço do sistema acessa

insert into categorias_servico (nome) values
  ('Premiação'), ('Lojas Vivo'), ('Agendamentos Reintegra'), ('Coletas em loja'), ('Chips')
on conflict (nome) do nothing;
