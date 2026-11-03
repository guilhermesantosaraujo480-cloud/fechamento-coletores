-- v13: robustez. (1) chave de envio única: repetir o envio depois de uma queda de internet não duplica a coleta.
--      (2) dividir/desfazer divisão numa operação única no banco (tudo ou nada). Aditivo; pode rodar mais de uma vez.
alter table coletas add column if not exists chave_envio text;
create unique index if not exists uq_coletas_chave_envio on coletas (chave_envio) where chave_envio is not null;

create or replace function public.dividir_coleta(p_id bigint, p_parceiro text)
returns table(novo_id bigint, parte_dono numeric, parte_parceiro numeric)
language plpgsql security invoker set search_path = public, pg_temp as $$
declare
  o coletas%rowtype; cent bigint; parc bigint; novo bigint;
begin
  select * into o from coletas where id = p_id for update;
  if not found then raise exception 'Coleta #% não encontrada.', p_id; end if;
  if p_parceiro is null or btrim(p_parceiro) = '' then raise exception 'Escolha o coletor parceiro.'; end if;
  if btrim(p_parceiro) = o.coletor then raise exception 'O parceiro precisa ser outro coletor.'; end if;
  if o.status is distinct from 'Aprovado' then raise exception 'Coleta #%: só coleta aprovada pode ser dividida.', p_id; end if;
  if coalesce(o.pago, false) then raise exception 'Coleta #%: já está marcada como paga.', p_id; end if;
  if o.divisao_de is not null or coalesce(btrim(o.dividida_com), '') <> '' then raise exception 'Coleta #%: já foi dividida.', p_id; end if;
  if coalesce(o.valor_total, 0) <= 0 then raise exception 'Coleta #%: sem valor para dividir.', p_id; end if;
  cent := round(o.valor_total * 100);
  parc := cent / 2;  -- o centavo que sobra fica com o dono
  insert into coletas (data, coletor, quantidade, foto_url, status, valor_total, pago, qtd_acrescimo, divisao_de, dividida_com)
  values (o.data, btrim(p_parceiro), o.quantidade, o.foto_url, 'Aprovado', parc / 100.0, false, 0, o.id, o.coletor)
  returning id into novo;
  update coletas set valor_total = (cent - parc) / 100.0, dividida_com = btrim(p_parceiro) where id = o.id;
  return query select novo, (cent - parc) / 100.0, parc / 100.0;
end $$;

create or replace function public.desfazer_divisao(p_filho bigint)
returns bigint
language plpgsql security invoker set search_path = public, pg_temp as $$
declare
  f coletas%rowtype; p coletas%rowtype;
begin
  select * into f from coletas where id = p_filho for update;
  if not found then raise exception 'Coleta #% não encontrada.', p_filho; end if;
  if f.divisao_de is null then raise exception 'Esta linha não é a parte de um parceiro.'; end if;
  if coalesce(f.pago, false) then raise exception 'A parte do parceiro já está marcada como paga. Desmarque o pagamento antes de desfazer.'; end if;
  select * into p from coletas where id = f.divisao_de for update;
  if not found then raise exception 'Coleta #% não encontrada.', f.divisao_de; end if;
  if coalesce(p.pago, false) then raise exception 'A coleta original já está marcada como paga. Desmarque o pagamento antes de desfazer.'; end if;
  if coalesce(btrim(p.dividida_com), '') <> '' then
    update coletas set valor_total = p.valor_total + f.valor_total, dividida_com = null where id = p.id;
  end if;
  delete from coletas where id = f.id;
  return p.id;
end $$;

revoke execute on function public.dividir_coleta(bigint, text) from public, anon, authenticated;
revoke execute on function public.desfazer_divisao(bigint) from public, anon, authenticated;
grant execute on function public.dividir_coleta(bigint, text) to service_role;
grant execute on function public.desfazer_divisao(bigint) to service_role;
