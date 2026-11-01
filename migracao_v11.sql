-- v11: fecha o acesso público (chave anon) aos dados. O sistema, a Edge Function e os workers usam a chave service_role, que ignora o RLS.
-- Sem política = a chave anon não lê nem grava nada (como já é nas outras tabelas). Pode rodar mais de uma vez.
drop policy if exists "Permitir Inserção Pública de Usuários" on usuarios;
drop policy if exists "Permitir Leitura Pública de Usuários" on usuarios;
drop policy if exists "Permitir Inserção Pública de Vales" on vales_coleta;
drop policy if exists "Permitir Leitura Pública de Vales" on vales_coleta;
drop policy if exists "Permitir tudo para todos" on premiacoes;
drop policy if exists "Permitir Inserção Pública de Coletas" on coletas;
drop policy if exists "Permitir inserção e leitura para usuários do app" on logs_comprovantes;
drop policy if exists "Permitir acesso total contas_email" on contas_email;
drop policy if exists "Permitir insercao publica de cliques" on cliques_email;
drop policy if exists "Permitir leitura para o painel" on cliques_email;
drop policy if exists "Permitir leitura publica de cliques" on cliques_email;
-- função interna do Supabase não deve ser chamável pela API pública
revoke execute on function public.rls_auto_enable() from anon, authenticated, public;
alter function public.limpar_historico_antigo(integer, integer) set search_path = public, pg_temp;
