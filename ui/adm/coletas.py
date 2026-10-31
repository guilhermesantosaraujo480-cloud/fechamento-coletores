"""Coletas: aprovar/recusar pendentes e corrigir status/pagamento dos lançamentos (com desfazer)."""
from datetime import date

import streamlit as st

from core import auditoria, dados, divisao, sessao
from core import financeiro as fin
from core.config import valor_por_coleta
from core.utils import brl, data_br, em_lotes
from ui.componentes import cabecalho, cartao, confirmar, erro_banco, metricas, mostrar_foto, navegacao, vazio

MAX_CARTOES = 24
MAX_LINHAS_TABELA = 500
MAX_APARELHOS = 500


def _como_data(texto):
    try:
        return date.fromisoformat(str(texto)[:10])
    except ValueError:
        return date.today()


def _editar(sb, linha, prefixo):
    """Corrige data, quantidade, aparelhos acrescentados e valor de uma coleta.

    `quantidade` e `valor_total` guardam o TOTAL (o que o coletor recebe); o acréscimo é só um controle interno
    para o administrador enxergar quantos aparelhos foram acrescentados — não aparece no fechamento."""
    if getattr(linha, "dividida_com", None) or int(getattr(linha, "divisao_de", 0) or 0) > 0:
        st.info("Esta coleta foi dividida entre dois coletores. Para editar, desfaça a divisão em **➗ Dividir coletas**.")
        return
    acr_atual = int(getattr(linha, "qtd_acrescimo", 0) or 0)
    qtd_atual = int(linha.quantidade)
    real_atual = max(qtd_atual - acr_atual, 0)
    a, b = st.columns(2)
    data_nova = a.date_input("Data", value=_como_data(linha.data), key=f"{prefixo}_dt_{linha.id}")
    real = b.number_input("Qtd que o coletor fez", min_value=0, max_value=MAX_APARELHOS, value=real_atual, step=1,
                          key=f"{prefixo}_re_{linha.id}")
    acr = a.number_input("➕ Aparelhos acrescentados", min_value=0, max_value=MAX_APARELHOS, value=acr_atual, step=1,
                         key=f"{prefixo}_ac_{linha.id}",
                         help="Só você vê. Entra na quantidade e no valor pagos, mas não aparece no fechamento.")
    total = int(real) + int(acr)
    sugerido = float(linha.valor_total) if total == qtd_atual else round(total * valor_por_coleta(), 2)
    valor = b.number_input("Valor total (R$)", min_value=0.0, value=float(sugerido), step=1.0, format="%.2f",
                           key=f"{prefixo}_vl_{linha.id}_{total}")
    st.caption(f"Total pago ao coletor: **{total} un · {brl(valor)}**"
               + (f" (sendo {int(acr)} acrescentados)" if acr else ""))
    if linha.status == "Aprovado":
        st.warning("Coleta já aprovada: a alteração muda o fechamento.")
    if st.button("💾 Salvar edição", key=f"{prefixo}_sv_{linha.id}", use_container_width=True):
        if total <= 0:
            st.error("A quantidade total precisa ser maior que zero. Para descartar, use Recusar.")
            return
        mudanca = {"data": str(data_nova), "quantidade": total, "valor_total": round(float(valor), 2)}
        if int(acr) > 0 or acr_atual > 0:  # só toca na coluna nova quando é necessário
            mudanca["qtd_acrescimo"] = int(acr)
        try:
            sb.table("coletas").update(mudanca).eq("id", int(linha.id)).execute()
        except Exception as erro:
            st.error(f"Não foi possível salvar. Se o erro citar `qtd_acrescimo`, rode o `migracao_v5.sql` no Supabase. Detalhe: {erro}")
            return
        auditoria.registrar(sb, sessao.usuario_atual()["usuario"], "coleta_editada",
                            f"id={linha.id} {linha.coletor}: qtd {qtd_atual}→{total}, acréscimo {acr_atual}→{int(acr)}, "
                            f"valor {linha.valor_total}→{mudanca['valor_total']}, data {linha.data}→{mudanca['data']}")
        dados.invalidar()
        st.toast("Coleta editada.", icon="✅")
        st.rerun()


def _decidir(sb, linha, status, parceiro=None):
    """Muda o status só se ainda estiver Pendente (evita dois admins decidirem a mesma coleta). Com `parceiro`, divide ao aprovar."""
    usuario = sessao.usuario_atual()["usuario"]
    mudou = sb.table("coletas").update({"status": status}).eq("id", int(linha.id)).eq("status", "Pendente").execute().data
    auditoria.registrar(sb, usuario, f"coleta_{status.lower()}",
                        f"id={linha.id} coletor={linha.coletor} qtd={linha.quantidade} valor={linha.valor_total}")
    if parceiro and status == "Aprovado" and mudou:
        try:
            divisao.dividir(sb, linha.id, parceiro)
            auditoria.registrar(sb, usuario, "coleta_dividida", f"id={linha.id} {linha.coletor} + {parceiro}")
        except divisao.ErroDivisao as erro:
            st.error(f"Aprovada, mas não dividi: {erro}")
            dados.invalidar()
            return
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

    try:
        nomes = list(dados.nomes_coletores(sb))
    except Exception:  # noqa: BLE001 — sem a lista, só some a opção de dividir
        nomes = []
    colunas = st.columns(3)
    for i, linha in enumerate(ordenadas.head(MAX_CARTOES).itertuples()):
        with colunas[i % 3]:
            with cartao():
                mostrar_foto(sb, linha.foto_url, miniatura=True, chave=f"pend_{linha.id}")
                st.markdown(f"**{linha.coletor}** · {linha.quantidade} un · {brl(linha.valor_total)}")
                st.caption(f"📅 {data_br(linha.data)}"
                           + (f" · ➕ {int(linha.qtd_acrescimo)} acrescentados" if linha.qtd_acrescimo else ""))
                with st.expander("✏️ Editar / acrescentar"):
                    _editar(sb, linha, "ed")
                parceiro = st.selectbox("➗ Dividir com (opcional)", ["—"] + [n for n in nomes if n != linha.coletor],
                                        key=f"dv_{linha.id}", help="Dois coletores com um só login: aprova e divide o valor meio a meio.")
                b1, b2 = st.columns(2)
                if b1.button("✓ Aprovar", key=f"ap_{linha.id}", type="primary", use_container_width=True):
                    _decidir(sb, linha, "Aprovado", None if parceiro == "—" else parceiro)
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
    tela = original[["data", "coletor", "quantidade", "qtd_acrescimo", "valor_total", "status", "pago", "dividida_com"]].copy()
    tela["dividida_com"] = tela["dividida_com"].fillna("")
    tela["data"] = tela["data"].map(data_br)
    st.caption("Edite **Status** e **Pago** direto na tabela e clique em salvar. Dá para reabrir uma coleta recusada.")
    editado = st.data_editor(
        tela, key="editor_coletas", use_container_width=True,
        disabled=["data", "coletor", "quantidade", "qtd_acrescimo", "valor_total", "dividida_com"],
        column_config={
            "data": "Data", "coletor": "Coletor", "quantidade": "Qtd", "qtd_acrescimo": "➕ Acresc.",
            "valor_total": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "dividida_com": "➗ Dividida com",
            "status": st.column_config.SelectboxColumn("Status", options=list(fin.STATUS), required=True),
            "pago": st.column_config.CheckboxColumn("Pago (controle)"),
        },
    )

    mudancas = []
    for id_, nova in editado.iterrows():
        antes = original.loc[id_]
        pago_novo = bool(nova["pago"]) and nova["status"] == "Aprovado"  # só aprovada pode estar paga
        if antes.get("dividida_com") and nova["status"] != "Aprovado":
            st.warning(f"Coleta #{id_} está dividida: desfaça a divisão antes de mudar o status.")
            continue
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

    with st.expander("✏️ Editar uma coleta (quantidade, acréscimo, valor ou data)"):
        rotulos = {int(r.id): f"#{r.id} · {data_br(r.data)} · {r.coletor} · {r.quantidade} un · {r.status}"
                   for r in ordenadas.itertuples()}
        escolhida = st.selectbox("Coleta", list(rotulos), format_func=lambda i: rotulos[i], key="ed_escolha")
        if escolhida is not None:
            linha = next(r for r in ordenadas.itertuples() if int(r.id) == int(escolhida))
            _editar(sb, linha, "edl")

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


def _dividir(sb, coletas):
    """Divide coletas aprovadas e não pagas entre dois coletores (50/50) — uma a uma ou em lote — e desfaz divisões."""
    usuario = sessao.usuario_atual()["usuario"]
    try:
        nomes = list(dados.nomes_coletores(sb))
    except Exception as erro:  # noqa: BLE001
        erro_banco(erro)
        return
    st.caption("Para dois coletores que usam o mesmo login: o valor é dividido **meio a meio** e cada um vê o total de aparelhos. "
               "Nos totais gerais os aparelhos contam uma vez só. Só coletas **aprovadas e não pagas**.")
    if coletas.empty:
        vazio("Nenhuma coleta no período.")
        return
    elegiveis = coletas[coletas.apply(lambda r: not divisao.motivo_de_nao_dividir(r), axis=1)].sort_values(["data", "id"], ascending=False)
    if elegiveis.empty:
        st.info("Nenhuma coleta elegível (aprovada, não paga, ainda não dividida) neste período.")
    else:
        rot = {int(r.id): f"#{r.id} · {data_br(r.data)} · {r.coletor} · {r.quantidade} un · {brl(r.valor_total)}"
               for r in elegiveis.head(MAX_LINHAS_TABELA).itertuples()}
        marcadas = st.multiselect("Coletas a dividir", list(rot), format_func=lambda i: rot[i], key="dv_sel")
        donos = {str(elegiveis[elegiveis["id"] == i]["coletor"].iloc[0]) for i in marcadas}
        parceiro = st.selectbox("Dividir com", ["—"] + [n for n in nomes if n not in donos or len(donos) > 1], key="dv_parc")
        if marcadas and parceiro != "—":
            ex = elegiveis[elegiveis["id"] == marcadas[0]].iloc[0]
            dono_v, parc_v = divisao.partes(ex["valor_total"])
            st.write(f"Exemplo (#{int(ex['id'])}): **{int(ex['quantidade'])} un** · {ex['coletor']} fica com {brl(dono_v)} e {parceiro} com {brl(parc_v)}.")
            if confirmar(f"Confirmo dividir {len(marcadas)} coleta(s) com {parceiro}", "chk_dividir") and st.button("➗ Dividir", type="primary"):
                feitas, falhas = 0, []
                for i in marcadas:
                    try:
                        divisao.dividir(sb, i, parceiro)
                        auditoria.registrar(sb, usuario, "coleta_dividida", f"id={i} + {parceiro}")
                        feitas += 1
                    except divisao.ErroDivisao as erro:
                        falhas.append(str(erro))
                dados.invalidar()
                if falhas:
                    st.error(" | ".join(falhas))
                st.toast(f"{feitas} coleta(s) dividida(s).", icon="✅")
                if not falhas:
                    st.rerun()
    divididas = coletas[coletas["divisao_de"] > 0].sort_values("id", ascending=False) if "divisao_de" in coletas else coletas.iloc[0:0]
    if not divididas.empty:
        with st.expander(f"↩️ Desfazer divisão ({len(divididas)})"):
            rot = {int(r.id): f"#{r.divisao_de} {r.dividida_com} ⇄ {r.coletor} · {data_br(r.data)} · {r.quantidade} un · {'pago' if r.pago else brl(r.valor_total)}"
                   for r in divididas.head(MAX_LINHAS_TABELA).itertuples()}
            escolha = st.selectbox("Divisão", list(rot), format_func=lambda i: rot[i], key="dv_undo")
            if st.button("↩️ Desfazer esta divisão", key="dv_undo_btn"):
                try:
                    pai = divisao.desfazer(sb, escolha)
                except divisao.ErroDivisao as erro:
                    st.error(str(erro))
                else:
                    auditoria.registrar(sb, usuario, "coleta_divisao_desfeita", f"original=#{pai}")
                    dados.invalidar()
                    st.toast("Divisão desfeita.", icon="✅")
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
    secao = navegacao(["⏳ Pendentes", "📑 Lançamentos do período", "➗ Dividir coletas"], "nav_coletas")
    if secao == "⏳ Pendentes":
        _pendentes(sb, pendentes)
    elif secao == "➗ Dividir coletas":
        _dividir(sb, coletas)
    else:
        _lancamentos(sb, coletas, filtro)
