"""Fechamento: resumo por coletor, recibo pronto para copiar e exportação para Excel."""
import streamlit as st

from core import dados
from core import financeiro as fin
from core.exportacao import gerar_excel
from core.utils import agora_br, brl, data_br
from ui.componentes import baixar_excel, cabecalho, cartao, erro_banco, metricas, vazio


def _abas_excel(resumo, coletas, vales, premios):
    aprov = coletas[coletas["status"] == "Aprovado"][["data", "coletor", "quantidade", "valor_total", "pago"]].copy()
    aprov["data"] = aprov["data"].map(data_br)
    v = vales[["data", "coletor", "valor_vale", "descricao"]].copy()
    v["data"] = v["data"].map(data_br)
    p = premios[["data", "coletor", "valor_premiacao", "descricao"]].copy()
    p["data"] = p["data"].map(data_br)
    return {
        "Resumo por Coletor": fin.adicionar_total(resumo),
        "Coletas aprovadas": aprov.rename(columns={"data": "Data", "coletor": "Coletor", "quantidade": "Qtd",
                                                   "valor_total": "Valor (R$)", "pago": "Pago"}),
        "Vales": v.rename(columns={"data": "Data", "coletor": "Coletor", "valor_vale": "Valor (R$)", "descricao": "Motivo"}),
        "Premiações": p.rename(columns={"data": "Data", "coletor": "Coletor", "valor_premiacao": "Valor (R$)",
                                        "descricao": "Motivo"}),
    }


def render(sb, filtro):
    try:  # sempre carrega todos os coletores: o resumo compara todo mundo
        coletas, vales, premios, _ = dados.carregar_financeiro(sb, filtro.ini, filtro.fim, "Todos")
        cadastrados = dados.nomes_coletores(sb, somente_ativos=False)
    except Exception as erro:
        erro_banco(erro)
        return

    cabecalho("💵 Fechamento financeiro", filtro.descricao)
    resumo = fin.resumo_por_coletor(coletas, vales, premios, cadastrados)
    if resumo.empty:
        vazio("Nenhum movimento no período.")
        return

    f = fin.calcular_fechamento(*(fin.filtrar_coletor(d, filtro.coletor) for d in (coletas, vales, premios)))
    metricas([("📱 Aparelhos", f"{f.aparelhos}"), ("💰 Bruto", brl(f.reais("bruto"))),
              ("🏅 Premiações (+)", brl(f.reais("premios"))), ("📉 Vales (−)", brl(f.reais("vales"))),
              ("🧮 Líquido", brl(f.reais("liquido")))])

    if filtro.coletor != "Todos":
        if f.liquido < 0:
            st.error(f"🔴 Os vales superaram a produção de {filtro.coletor} em **{brl(abs(f.reais('liquido')))}**.")
        elif f.liquido == 0:
            st.success("🟢 Conta zerada: nada a repassar neste período.")
        else:
            st.info(f"🔵 Acerto a fazer com {filtro.coletor}: **{brl(f.reais('liquido'))}**")

    esquerda, direita = st.columns([3, 2])
    with esquerda:
        with cartao():
            st.markdown("**Resumo por coletor**")
            tabela = fin.formatar_moeda(fin.adicionar_total(resumo), ["Bruto", "Premiações", "Vales", "Líquido", "Não pago"])
            st.dataframe(tabela, hide_index=True, use_container_width=True)
            baixar_excel("📊 Baixar relatório em Excel (.xlsx)",
                         gerar_excel(_abas_excel(resumo, coletas, vales, premios)),
                         f"relatorio_coletas_{filtro.ini:%Y%m%d}_a_{filtro.fim:%Y%m%d}.xlsx")
    with direita:
        with cartao():
            st.markdown("**Recibo para copiar**")
            if filtro.coletor == "Todos":
                st.caption("Escolha um coletor nos filtros da barra lateral para gerar o recibo dele.")
            else:
                st.code(fin.texto_recibo(filtro.coletor, filtro.ini, filtro.fim, f, agora_br()), language="text")
