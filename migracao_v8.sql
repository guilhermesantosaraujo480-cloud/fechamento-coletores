-- =====================================================================
-- MIGRAÇÃO V8 - Supabase: SQL Editor > New query > Run  (pode rodar mais de uma vez; nada é apagado)
--   Vales: guarda o código da transação lido do comprovante (evita lançar o mesmo comprovante duas vezes)
-- =====================================================================
alter table vales_coleta add column if not exists comprovante_id text;
create index if not exists idx_vales_comprovante on vales_coleta (comprovante_id) where comprovante_id is not null;
