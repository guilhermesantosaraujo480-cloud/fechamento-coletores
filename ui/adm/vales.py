"""Vales (adiantamentos): lançar com foto do comprovante, consultar e corrigir."""
import streamlit as st

from core import armazenamento, auditoria, dados, sessao
from core import financeiro as fin
from core.utils import brl, data_br, hoje_br
from ui.componentes import cabecalho, cartao, confirmar, erro_banco, metricas, mostrar_foto, vazio


def _formulario(sb, coletores):
    usuario = sessao.usuario_atual()["usuario"]
    with cartao():
        st.markdown("**➕ Lançar novo vale**")
        if not coletores:
            vazio("Nenhum coletor cadastrado.")
            return
        with st.form("form_vale", clear_on_submit=True):
            coletor = st.selectbox("Coletor", coletores)
            valor = st.number_input("Valor (R$)", min_value=0.01, step=5.0, value=10.0, format="%.2f")
            data = st.date_input("Data", value=hoje_br(), format="DD/MM/YYYY")
            motivo = st.text_input("Motivo (opcional)", value="Adiantamento de Coletas")
            foto = st.file_uploader("Foto do comprovante", type=["png", "jpg", "jpeg"])
            enviar = st.form_submit_button("Lançar vale", type="primary", use_container_width=True)
        if not enviar:
            return
        if not foto:
            st.error("Adicione a foto do comprovante antes de lançar.")
            return
        try:
            with st.spinner("Salvando..."):
                caminho = armazenamento.salvar_foto(sb, foto, f"vale_{usuario}")
                sb.table("vales_coleta").insert({
                    "data": str(data), "coletor": coletor, "valor_vale": round(float(valor), 2),
                    "descricao": motivo.strip(), "foto_url": caminho,
                }).execute()
            auditoria.registrar(sb, usuario, "vale_lancado", f"{coletor} {brl(valor)} em {data}")
            dados.invalidar()
            st.toast(f"Vale de {brl(valor)} lançado.", icon="✅")
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))
        except Exception as erro:
            st.error(f"Erro ao salvar o vale: {erro}")


def _historico(sb, vales):
    usuario = sessao.usuario_atual()["usuario"]
    with cartao():
        st.markdown("**📋 Vales do período**")
        if vales.empty:
            vazio("Nenhum vale encontrado para os filtros.")
            return
        ordenados = vales.sort_values(["data", "id"], ascending=False)
        metricas([("Quantidade", f"{len(ordenados)}"), ("Total em vales", brl(ordenados["valor_vale"].sum()))])
        tabela = ordenados[["data", "coletor", "valor_vale", "descricao"]].copy()
        tabela["data"] = tabela["data"].map(data_br)
        st.dataframe(fin.formatar_moeda(tabela.rename(columns={
            "data": "Data", "coletor": "Coletor", "valor_vale": "Valor", "descricao": "Motivo"}), ["Valor"]),
            hide_index=True, use_container_width=True)

        rotulos = {int(r.id): f"{data_br(r.data)} · {r.coletor} · {brl(r.valor_vale)}" for r in ordenados.head(200).itertuples()}
        escolhido = st.selectbox("Ver comprovante / corrigir", list(rotulos), format_func=rotulos.get,
                                 index=None, placeholder="Escolha um vale...")
        if escolhido is None:
            return
        linha = ordenados[ordenados["id"] == escolhido].iloc[0]
        mostrar_foto(sb, linha["foto_url"], largura=260, legenda="Comprovante do vale")
        with st.expander("🗑️ Excluir este vale (lançado por engano)"):
            if confirmar("Confirmo a exclusão", f"chk_del_vale_{escolhido}") and st.button("Excluir vale", key=f"del_vale_{escolhido}"):
                sb.table("vales_coleta").delete().eq("id", int(escolhido)).execute()
                auditoria.registrar(sb, usuario, "vale_excluido", rotulos[escolhido])
                dados.invalidar()
                st.toast("Vale excluído.", icon="🗑️")
                st.rerun()


def render(sb, filtro):
    try:
        _, vales, _, _ = dados.carregar_financeiro(sb, filtro.ini, filtro.fim, filtro.coletor)
        coletores = dados.nomes_coletores(sb)
    except Exception as erro:
        erro_banco(erro)
        return
    cabecalho("📉 Vales", filtro.descricao)
    esquerda, direita = st.columns([2, 3])
    with esquerda:
        _formulario(sb, coletores)
    with direita:
        _historico(sb, vales)
