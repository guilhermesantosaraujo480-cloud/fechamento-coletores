-- =====================================================================
-- MIGRAÇÃO V9 - Supabase: SQL Editor > New query > Run  (pode rodar mais de uma vez; nada é apagado)
--   Divisão de coletas entre dois coletores (quando dois trabalham juntos com um só login):
--   a coleta original fica com a parte do dono e nasce uma linha para o parceiro com a outra parte.
--   divisao_de  = id da coleta original (só na linha do parceiro)
--   dividida_com = nome do outro coletor (nas duas linhas)
-- =====================================================================
alter table coletas add column if not exists divisao_de bigint;
alter table coletas add column if not exists dividida_com text;
create index if not exists idx_coletas_divisao_de on coletas (divisao_de) where divisao_de is not null;
