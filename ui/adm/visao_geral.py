"""Visão geral: números do período, gráfico diário e ranking de coletores."""
import streamlit as st

from core import dados
from core import financeiro as fin
from core.utils import brl
from ui.componentes import cabecalho, cartao, erro_banco, metricas


def render(sb, filtro):
    try:
        coletas, vales, premios, pendentes = dados.carregar_financeiro(sb, filtro.ini, filtro.fim, filtro.coletor)
        coletores = dados.nomes_coletores(sb)
    except Exception as erro:
        erro_banco(erro)
        return

    f = fin.calcular_fechamento(coletas, vales, premios)
    cabecalho("📊 Visão geral", filtro.descricao)

    if len(pendentes):
        st.warning(f"⏳ **{len(pendentes)} coleta(s)** aguardando aprovação (de qualquer data) — abra **Coletas**.")

    metricas([
        ("📱 Aparelhos", f"{f.aparelhos}", "Somente coletas aprovadas"),
        ("💰 Bruto", brl(f.reais("bruto"))),
        ("🏅 Premiações (+)", brl(f.reais("premios"))),
        ("📉 Vales (−)", brl(f.reais("vales"))),
        ("🧮 Líquido", brl(f.reais("liquido")), "Bruto + premiações − vales"),
    ])
    dias = (filtro.fim - filtro.ini).days + 1
    metricas([
        ("⏳ Aguardando aprovação", f"{len(pendentes)}"),
        ("💳 Aprovado e não pago", brl(f.reais("nao_pago")), "Coletas aprovadas ainda não marcadas como pagas"),
        ("📆 Média por dia", f"{f.aparelhos / max(dias, 1):.1f} un"),
    ])

    esquerda, direita = st.columns([3, 2])
    with esquerda:
        with cartao():
            st.markdown("**Aparelhos aprovados por dia**" if dias <= 92 else "**Aparelhos aprovados por mês**")
            serie = fin.serie_diaria(coletas, filtro.ini, filtro.fim)
            if serie["Aparelhos"].sum() == 0:
                st.caption("Sem coletas aprovadas no período.")
            else:
                st.bar_chart(serie, height=280)
    with direita:
        with cartao():
            st.markdown("**Ranking de coletores**")
            resumo = fin.resumo_por_coletor(coletas, vales, premios, coletores if filtro.coletor == "Todos" else ())
            if resumo.empty:
                st.caption("Nenhum movimento no período.")
            else:
                ranking = resumo.sort_values(["Aparelhos", "Líquido"], ascending=False)[["Coletor", "Aparelhos", "Líquido"]]
                st.dataframe(fin.formatar_moeda(ranking, ["Líquido"]), hide_index=True, use_container_width=True)

    negativos = fin.resumo_por_coletor(coletas, vales, premios)
    negativos = negativos[negativos["Líquido"] < 0] if not negativos.empty else negativos
    if not negativos.empty:
        nomes = ", ".join(f"{r.Coletor} ({brl(r.Líquido)})" for r in negativos.itertuples())
        st.error(f"🔴 Vales superaram a produção de: {nomes}")
