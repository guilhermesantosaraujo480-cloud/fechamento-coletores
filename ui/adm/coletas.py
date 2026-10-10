"""Coletas: aprovar/recusar pendentes e corrigir status/pagamento dos lançamentos (com desfazer)."""
import streamlit as st

from core import auditoria, dados, sessao
from core import financeiro as fin
from core.utils import brl, data_br, em_lotes
from ui.componentes import cabecalho, cartao, confirmar, erro_banco, metricas, mostrar_foto, navegacao, vazio

MAX_CARTOES = 24
MAX_LINHAS_TABELA = 500


def _decidir(sb, linha, status):
    """Muda o status só se ainda estiver Pendente (evita dois admins decidirem a mesma coleta)."""
    usuario = sessao.usuario_atual()["usuario"]
    sb.table("coletas").update({"status": status}).eq("id", int(linha.id)).eq("status", "Pendente").execute()
    auditoria.registrar(sb, usuario, f"coleta_{status.lower()}",
                        f"id={linha.id} coletor={linha.coletor} qtd={linha.quantidade} valor={linha.valor_total}")
    dados.invalidar()
    st.toast(f"Coleta {status.lower()}.", icon="✅")
    st.rerun()


def _pendentes(sb, pendentes):
    if pendentes.empty:
        vazio("🎉 Nenhuma coleta pendente de aprovação.")
        return
    total = len(pendentes)
    ordenadas = pendentes.sort_values(["data", "id"])
    st.caption(f"{total} pendente(s) — de qualquer data. Mostrando as {min(total, MAX_CARTOES)} mais antigas.")

    with st.expander("⚡ Aprovar todas as pendentes de uma vez"):
        st.write(f"Isso aprova **{total}** coleta(s) sem olhar as fotos. Use só se já conferiu.")
        if confirmar("Sim, quero aprovar todas", "chk_aprovar_todas") and st.button("Aprovar todas", type="primary"):
            ids = [int(i) for i in ordenadas["id"]]
            for lote in em_lotes(ids, 200):
                sb.table("coletas").update({"status": "Aprovado"}).in_("id", lote).eq("status", "Pendente").execute()
            auditoria.registrar(sb, sessao.usuario_atual()["usuario"], "coleta_aprovar_todas", f"{len(ids)} coletas")
            dados.invalidar()
            st.toast(f"{len(ids)} coletas aprovadas.", icon="✅")
            st.rerun()

    colunas = st.columns(3)
    for i, linha in enumerate(ordenadas.head(MAX_CARTOES).itertuples()):
        with colunas[i % 3]:
            with cartao():
                mostrar_foto(sb, linha.foto_url)
                st.markdown(f"**{linha.coletor}** · {linha.quantidade} un · {brl(linha.valor_total)}")
                st.caption(f"📅 {data_br(linha.data)}")
                b1, b2 = st.columns(2)
                if b1.button("✓ Aprovar", key=f"ap_{linha.id}", type="primary", use_container_width=True):
                    _decidir(sb, linha, "Aprovado")
                if b2.button("✕ Recusar", key=f"rec_{linha.id}", use_container_width=True):
                    _decidir(sb, linha, "Recusado")


def _lancamentos(sb, coletas, filtro):
    usuario = sessao.usuario_atual()["usuario"]
    if coletas.empty:
        vazio("Nenhum lançamento no período.")
        return

    ordenadas = coletas.sort_values(["data", "id"], ascending=False).head(MAX_LINHAS_TABELA)
    if len(coletas) > MAX_LINHAS_TABELA:
        st.caption(f"Mostrando os {MAX_LINHAS_TABELA} mais recentes de {len(coletas)}. Estreite o período para ver os demais.")

    original = ordenadas.set_index("id")
    tela = original[["data", "coletor", "quantidade", "valor_total", "status", "pago"]].copy()
    tela["data"] = tela["data"].map(data_br)
    st.caption("Edite **Status** e **Pago** direto na tabela e clique em salvar. Dá para reabrir uma coleta recusada.")
    editado = st.data_editor(
        tela, key="editor_coletas", use_container_width=True,
        disabled=["data", "coletor", "quantidade", "valor_total"],
        column_config={
            "data": "Data", "coletor": "Coletor", "quantidade": "Qtd",
            "valor_total": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "status": st.column_config.SelectboxColumn("Status", options=list(fin.STATUS), required=True),
            "pago": st.column_config.CheckboxColumn("Pago (controle)"),
        },
    )

    mudancas = []
    for id_, nova in editado.iterrows():
        antes = original.loc[id_]
        pago_novo = bool(nova["pago"]) and nova["status"] == "Aprovado"  # só aprovada pode estar paga
        if nova["status"] != antes["status"] or pago_novo != bool(antes["pago"]):
            mudancas.append((int(id_), nova["status"], pago_novo, antes))

    if st.button(f"💾 Salvar {len(mudancas)} alteração(ões)", type="primary",
                 disabled=not mudancas, key="salvar_editor_coletas"):
        for id_, status, pago, antes in mudancas:
            sb.table("coletas").update({"status": status, "pago": pago}).eq("id", id_).execute()
            auditoria.registrar(sb, usuario, "coleta_editada",
                                f"id={id_} {antes['coletor']}: status {antes['status']}→{status}, pago {bool(antes['pago'])}→{pago}")
        dados.invalidar()
        st.toast("Alterações salvas.", icon="✅")
        st.rerun()

    if filtro.coletor != "Todos":
        a_pagar = coletas[(coletas["status"] == "Aprovado") & (~coletas["pago"])]
        if not a_pagar.empty:
            with st.expander(f"💰 Marcar como pagas todas as aprovadas de {filtro.coletor} ({len(a_pagar)})"):
                st.write(f"Total: **{brl(a_pagar['valor_total'].sum())}**")
                if confirmar("Confirmo que já paguei este valor", "chk_pagar_todas") and st.button("Marcar todas como pagas"):
                    ids = [int(i) for i in a_pagar["id"]]
                    for lote in em_lotes(ids, 200):
                        sb.table("coletas").update({"pago": True}).in_("id", lote).execute()
                    auditoria.registrar(sb, usuario, "coleta_pagar_todas", f"{filtro.coletor}: {len(ids)} coletas")
                    dados.invalidar()
                    st.toast("Coletas marcadas como pagas.", icon="✅")
                    st.rerun()


def render(sb, filtro):
    try:
        coletas, _, _, pendentes = dados.carregar_financeiro(sb, filtro.ini, filtro.fim, filtro.coletor)
    except Exception as erro:
        erro_banco(erro)
        return
    cabecalho("📋 Coletas", filtro.descricao)
    f = fin.calcular_fechamento(coletas, fin.df_vales([]), fin.df_premios([]))
    metricas([("⏳ Pendentes (todas as datas)", f"{len(pendentes)}"),
              ("✅ Aprovadas no período", f"{f.aparelhos} un"),
              ("💳 Aprovado e não pago", brl(f.reais("nao_pago")))])
    secao = navegacao(["⏳ Pendentes", "📑 Lançamentos do período"], "nav_coletas")
    if secao == "⏳ Pendentes":
        _pendentes(sb, pendentes)
    else:
        _lancamentos(sb, coletas, filtro)
