"""Premiações e serviços extras."""
import streamlit as st

from core import auditoria, dados, sessao
from core import financeiro as fin
from core.utils import brl, data_br, hoje_br
from ui.componentes import cabecalho, cartao, confirmar, erro_banco, metricas, vazio


def _formulario(sb, coletores):
    usuario = sessao.usuario_atual()["usuario"]
    with cartao():
        st.markdown("**➕ Lançar premiação / serviço extra**")
        if not coletores:
            vazio("Nenhum coletor cadastrado.")
            return
        with st.form("form_premio", clear_on_submit=True):
            coletor = st.selectbox("Coletor", coletores)
            valor = st.number_input("Valor (R$)", min_value=0.01, step=5.0, value=50.0, format="%.2f")
            data = st.date_input("Data", value=hoje_br(), format="DD/MM/YYYY")
            motivo = st.text_input("Descrição / motivo", value="Meta Atingida")
            enviar = st.form_submit_button("Lançar premiação", type="primary", use_container_width=True)
        if not enviar:
            return
        try:
            sb.table("premiacoes").insert({
                "data": str(data), "coletor": coletor, "valor_premiacao": round(float(valor), 2),
                "descricao": motivo.strip(),
            }).execute()
            auditoria.registrar(sb, usuario, "premiacao_lancada", f"{coletor} {brl(valor)} em {data}")
            dados.invalidar()
            st.toast(f"Premiação de {brl(valor)} lançada.", icon="✅")
            st.rerun()
        except Exception as erro:
            st.error(f"Erro ao salvar a premiação: {erro}")


def _historico(sb, premios):
    usuario = sessao.usuario_atual()["usuario"]
    with cartao():
        st.markdown("**📋 Premiações do período**")
        if premios.empty:
            vazio("Nenhuma premiação no período.")
            return
        ordenadas = premios.sort_values(["data", "id"], ascending=False)
        metricas([("Quantidade", f"{len(ordenadas)}"), ("Total", brl(ordenadas["valor_premiacao"].sum()))])
        tabela = ordenadas[["data", "coletor", "valor_premiacao", "descricao"]].copy()
        tabela["data"] = tabela["data"].map(data_br)
        st.dataframe(fin.formatar_moeda(tabela.rename(columns={
            "data": "Data", "coletor": "Coletor", "valor_premiacao": "Valor", "descricao": "Motivo"}), ["Valor"]),
            hide_index=True, use_container_width=True)
        rotulos = {int(r.id): f"{data_br(r.data)} · {r.coletor} · {brl(r.valor_premiacao)}" for r in ordenadas.head(200).itertuples()}
        escolhida = st.selectbox("Corrigir lançamento", list(rotulos), format_func=rotulos.get,
                                 index=None, placeholder="Escolha uma premiação...")
        if escolhida is not None:
            with st.expander("🗑️ Excluir esta premiação (lançada por engano)"):
                if confirmar("Confirmo a exclusão", f"chk_del_prem_{escolhida}") and st.button("Excluir premiação", key=f"del_prem_{escolhida}"):
                    sb.table("premiacoes").delete().eq("id", int(escolhida)).execute()
                    auditoria.registrar(sb, usuario, "premiacao_excluida", rotulos[escolhida])
                    dados.invalidar()
                    st.toast("Premiação excluída.", icon="🗑️")
                    st.rerun()


def render(sb, filtro):
    try:
        _, _, premios, _ = dados.carregar_financeiro(sb, filtro.ini, filtro.fim, filtro.coletor)
        coletores = dados.nomes_coletores(sb)
    except Exception as erro:
        erro_banco(erro)
        return
    cabecalho("🏅 Premiações e serviços extras", filtro.descricao)
    esquerda, direita = st.columns([2, 3])
    with esquerda:
        _formulario(sb, coletores)
    with direita:
        _historico(sb, premios)
