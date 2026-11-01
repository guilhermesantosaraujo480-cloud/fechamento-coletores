"""Serviços e premiações: lançamentos extras por categoria (Premiação, Lojas Vivo, Agendamentos Reintegra, Coletas em loja, Chips...)."""
import streamlit as st

from core import auditoria, dados, sessao
from core import financeiro as fin
from core.utils import brl, data_br, hoje_br
from ui.componentes import cabecalho, cartao, confirmar, erro_banco, metricas, vazio


def _nova_categoria(sb):
    usuario = sessao.usuario_atual()["usuario"]
    with st.expander("➕ Nova categoria"):
        nome = st.text_input("Nome da categoria", key="cat_nova", placeholder="Ex.: Entrega de chips")
        if st.button("Adicionar categoria", key="cat_add") and nome.strip():
            try:
                sb.table("categorias_servico").upsert({"nome": nome.strip(), "ativo": True}).execute()
            except Exception as erro:  # noqa: BLE001
                st.error(f"Não consegui salvar. Rode o `migracao_v10.sql` no Supabase. Detalhe: {erro}")
                return
            auditoria.registrar(sb, usuario, "categoria_servico_criada", nome.strip())
            dados.invalidar()
            st.toast(f"Categoria '{nome.strip()}' criada.", icon="✅")
            st.rerun()


def _formulario(sb, coletores, categorias):
    usuario = sessao.usuario_atual()["usuario"]
    with cartao():
        st.markdown("**➕ Lançar serviço / premiação**")
        if not coletores:
            vazio("Nenhum coletor cadastrado.")
            return
        with st.form("form_premio", clear_on_submit=True):
            coletor = st.selectbox("Coletor", coletores)
            categoria = st.selectbox("Categoria", categorias)
            valor = st.number_input("Valor (R$)", min_value=0.01, step=5.0, value=50.0, format="%.2f")
            data = st.date_input("Data", value=hoje_br(), format="DD/MM/YYYY")
            motivo = st.text_input("Descrição (opcional)", value="")
            enviar = st.form_submit_button("Lançar", type="primary", use_container_width=True)
        if enviar:
            linha = {"data": str(data), "coletor": coletor, "valor_premiacao": round(float(valor), 2),
                     "descricao": motivo.strip(), "categoria": categoria}
            try:
                sb.table("premiacoes").insert(linha).execute()
            except Exception as erro:
                st.error(f"Erro ao salvar: {erro}")
                return
            auditoria.registrar(sb, usuario, "premiacao_lancada", f"{coletor} · {categoria} · {brl(valor)} em {data}")
            dados.invalidar()
            st.toast(f"{categoria}: {brl(valor)} lançado.", icon="✅")
            st.rerun()
        _nova_categoria(sb)


def _historico(sb, premios):
    usuario = sessao.usuario_atual()["usuario"]
    with cartao():
        st.markdown("**📋 Lançamentos do período**")
        if premios.empty:
            vazio("Nenhum lançamento no período.")
            return
        ordenadas = premios.sort_values(["data", "id"], ascending=False)
        metricas([("Quantidade", f"{len(ordenadas)}"), ("Total", brl(ordenadas["valor_premiacao"].sum()))])
        por_cat = fin.servicos_por_categoria(ordenadas)
        if por_cat:
            st.caption(" · ".join(f"{k}: {brl(v / 100)}" for k, v in por_cat.items()))
        tabela = ordenadas[["data", "coletor", "categoria", "valor_premiacao", "descricao"]].copy()
        tabela["data"] = tabela["data"].map(data_br)
        st.dataframe(fin.formatar_moeda(tabela.rename(columns={
            "data": "Data", "coletor": "Coletor", "categoria": "Categoria", "valor_premiacao": "Valor",
            "descricao": "Descrição"}), ["Valor"]), hide_index=True, use_container_width=True)
        rotulos = {int(r.id): f"{data_br(r.data)} · {r.coletor} · {r.categoria} · {brl(r.valor_premiacao)}"
                   for r in ordenadas.head(200).itertuples()}
        escolhida = st.selectbox("Corrigir lançamento", list(rotulos), format_func=rotulos.get,
                                 index=None, placeholder="Escolha um lançamento...")
        if escolhida is not None:
            with st.expander("🗑️ Excluir este lançamento (feito por engano)"):
                if confirmar("Confirmo a exclusão", f"chk_del_prem_{escolhida}") and st.button("Excluir", key=f"del_prem_{escolhida}"):
                    sb.table("premiacoes").delete().eq("id", int(escolhida)).execute()
                    auditoria.registrar(sb, usuario, "premiacao_excluida", rotulos[escolhida])
                    dados.invalidar()
                    st.toast("Lançamento excluído.", icon="🗑️")
                    st.rerun()


def render(sb, filtro):
    try:
        _, _, premios, _ = dados.carregar_financeiro(sb, filtro.ini, filtro.fim, filtro.coletor)
        coletores = dados.nomes_coletores(sb)
    except Exception as erro:
        erro_banco(erro)
        return
    categorias = dados.categorias_servico(sb)
    cabecalho("🏅 Serviços e premiações", filtro.descricao)
    esquerda, direita = st.columns([2, 3])
    with esquerda:
        _formulario(sb, coletores, categorias)
    with direita:
        _historico(sb, premios)
