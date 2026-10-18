"""Visão geral: números do período, gráfico diário e ranking de coletores."""
from datetime import timedelta

import streamlit as st

from core import dados
from core import financeiro as fin
from core.utils import brl, limites_quinzena
from ui.componentes import cabecalho, cartao, erro_banco, metricas


def _acrescimos(sb, coletas, filtro):
    """Controle interno: quantos aparelhos foram acrescentados aos coletores (por coletor e por quinzena)."""
    por_coletor = fin.acrescimos_por_coletor(coletas)
    with cartao():
        st.markdown("**➕ Aparelhos acrescentados** — controle interno (não aparece no Fechamento)")
        if por_coletor.empty:
            st.caption("Nenhum aparelho acrescentado neste período.")
        else:
            st.dataframe(por_coletor, hide_index=True, use_container_width=True)
        if st.toggle("Ver as últimas 6 quinzenas", key="ver_acrescimos_quinzenas"):
            fim_q = limites_quinzena(filtro.fim)[1]
            inicio = fin.quinzenas_antes(fim_q + timedelta(days=1), 6)[0][0]
            try:
                historico, _, _, _ = dados.carregar_financeiro(sb, inicio, fim_q, "Todos")
            except Exception as erro:
                erro_banco(erro)
                return
            st.dataframe(fin.acrescimos_por_quinzena(historico), hide_index=True, use_container_width=True)


def render(sb, filtro):
    try:
        coletas, vales, premios, pendentes = dados.carregar_financeiro(sb, filtro.ini, filtro.fim, filtro.coletor)
        coletores = dados.nomes_coletores(sb)
        saldos = dados.saldos_anteriores(sb, filtro.ini, filtro.coletor)
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
    acrescidos = fin.acrescimos(coletas)
    anterior = sum(saldos.values())
    metricas([
        ("⏳ Aguardando aprovação", f"{len(pendentes)}"),
        ("💳 Aprovado e não pago", brl(f.reais("nao_pago")), "Coletas aprovadas ainda não marcadas como pagas"),
        ("📆 Média por dia", f"{f.aparelhos / max(dias, 1):.1f} un"),
        ("↩️ Saldo anterior", brl(anterior / 100),
         "Vales que passaram da produção nas quinzenas anteriores (é descontado em 'A pagar', no Fechamento)"),
        ("➕ Acrescentados", f"{acrescidos} un",
         f"Aparelhos acrescentados às coletas aprovadas do período ({acrescidos / f.aparelhos * 100:.1f}% do total). "
         "Só você vê: não aparece no Fechamento." if f.aparelhos else "Aparelhos acrescentados (só você vê)."),
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
            resumo = fin.resumo_por_coletor(coletas, vales, premios, coletores if filtro.coletor == "Todos" else (), saldos)
            if resumo.empty:
                st.caption("Nenhum movimento no período.")
            else:
                # 'A pagar' = líquido do período + saldo devedor das quinzenas anteriores (igual ao Fechamento)
                ranking = resumo.sort_values(["Aparelhos", "A pagar"], ascending=False)[["Coletor", "Aparelhos", "A pagar"]]
                st.dataframe(fin.formatar_moeda(ranking, ["A pagar"]), hide_index=True, use_container_width=True)

    _acrescimos(sb, coletas, filtro)

    negativos = fin.resumo_por_coletor(coletas, vales, premios, (), saldos)
    negativos = negativos[negativos["A pagar"] < 0] if not negativos.empty else negativos
    if not negativos.empty:
        nomes = ", ".join(f"{n} ({brl(v)})" for n, v in zip(negativos["Coletor"], negativos["A pagar"]))
        st.error(f"🔴 Vales superaram a produção de: {nomes}")
