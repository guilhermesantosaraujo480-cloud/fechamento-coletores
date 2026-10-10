"""Extrato do coletor: quanto ele produziu, recebeu de extras e já retirou em vales."""
import streamlit as st

from core import dados, sessao
from core import financeiro as fin
from core.utils import PERIODOS, brl, data_br, hoje_br, periodo_por_nome
from ui.componentes import cabecalho, cartao, erro_banco, metricas, mostrar_foto, navegacao, vazio

ROTULO_STATUS = {"Aprovado": "🟢 Aprovada", "Pendente": "🟡 Aguardando aprovação", "Recusado": "🔴 Recusada"}


def _periodo():
    hoje = hoje_br()
    nome = st.selectbox("Período", PERIODOS, index=PERIODOS.index("Quinzena atual"), key="c_periodo")
    if nome == "Personalizado":
        c1, c2 = st.columns(2)
        ini = c1.date_input("De", value=hoje.replace(day=1), key="c_ini", format="DD/MM/YYYY")
        fim = c2.date_input("Até", value=hoje, key="c_fim", format="DD/MM/YYYY")
        return (fim, ini) if ini > fim else (ini, fim)
    return periodo_por_nome(nome, hoje)


def _envios(sb, coletas):
    if coletas.empty:
        vazio("Nenhum envio no período.")
        return
    ordenadas = coletas.sort_values(["data", "id"], ascending=False)
    tabela = ordenadas[["data", "quantidade", "valor_total", "status", "pago"]].copy()
    tabela["data"] = tabela["data"].map(data_br)
    tabela["situacao"] = [("✅ Pago" if p else "⏳ Aguardando acerto") if s == "Aprovado" else "—"
                          for s, p in zip(ordenadas["status"], ordenadas["pago"])]
    tabela["status"] = tabela["status"].map(lambda s: ROTULO_STATUS.get(s, s))
    tabela["valor_total"] = tabela["valor_total"].map(brl)
    st.dataframe(tabela[["data", "quantidade", "valor_total", "status", "situacao"]].rename(columns={
        "data": "Data", "quantidade": "Qtd", "valor_total": "Valor", "status": "Status", "situacao": "Pagamento"}),
        hide_index=True, use_container_width=True)
    rotulos = {int(r.id): f"{data_br(r.data)} · {r.quantidade} un · {ROTULO_STATUS.get(r.status, r.status)}"
               for r in ordenadas.head(100).itertuples()}
    escolhido = st.selectbox("Ver foto de um envio", list(rotulos), format_func=rotulos.get,
                             index=None, placeholder="Escolha um envio...")
    if escolhido is not None:
        mostrar_foto(sb, ordenadas[ordenadas["id"] == escolhido].iloc[0]["foto_url"], largura=260)


def _vales(sb, vales):
    if vales.empty:
        vazio("Nenhum vale no período.")
        return
    ordenados = vales.sort_values(["data", "id"], ascending=False)
    tabela = ordenados[["data", "valor_vale", "descricao"]].copy()
    tabela["data"] = tabela["data"].map(data_br)
    tabela["valor_vale"] = tabela["valor_vale"].map(brl)
    st.dataframe(tabela.rename(columns={"data": "Data", "valor_vale": "Valor", "descricao": "Motivo"}),
                 hide_index=True, use_container_width=True)
    rotulos = {int(r.id): f"{data_br(r.data)} · {brl(r.valor_vale)}" for r in ordenados.head(100).itertuples()}
    escolhido = st.selectbox("Ver comprovante de um vale", list(rotulos), format_func=rotulos.get,
                             index=None, placeholder="Escolha um vale...")
    if escolhido is not None:
        mostrar_foto(sb, ordenados[ordenados["id"] == escolhido].iloc[0]["foto_url"], largura=260)


def _premios(premios):
    if premios.empty:
        vazio("Nenhuma premiação no período.")
        return
    tabela = premios.sort_values(["data", "id"], ascending=False)[["data", "valor_premiacao", "descricao"]].copy()
    tabela["data"] = tabela["data"].map(data_br)
    tabela["valor_premiacao"] = tabela["valor_premiacao"].map(brl)
    st.dataframe(tabela.rename(columns={"data": "Data", "valor_premiacao": "Valor", "descricao": "Motivo"}),
                 hide_index=True, use_container_width=True)


def render(sb):
    nome = sessao.usuario_atual()["nome_completo"]
    cabecalho("📊 Meu extrato")
    ini, fim = _periodo()
    try:
        coletas, vales, premios, n_pendentes = dados.carregar_extrato(sb, nome, ini, fim)
    except Exception as erro:
        erro_banco(erro)
        return
    f = fin.calcular_fechamento(coletas, vales, premios)
    metricas([("📱 Aparelhos aprovados", f"{f.aparelhos}"), ("💰 Bruto", brl(f.reais("bruto"))),
              ("🏅 Premiações (+)", brl(f.reais("premios"))), ("📉 Vales (−)", brl(f.reais("vales"))),
              ("🧮 Líquido", brl(f.reais("liquido")))])
    try:
        anterior = dados.saldos_anteriores(sb, ini, nome).get(nome, 0)
    except Exception:
        anterior = 0
    if anterior:
        st.warning(f"↩️ Você tem **{brl(abs(anterior) / 100)}** de vales que passaram da produção na quinzena anterior. "
                   f"Esse valor é descontado automaticamente: a pagar agora = **{brl((f.liquido + anterior) / 100)}**.")
    if n_pendentes:
        st.info(f"🟡 Você tem **{n_pendentes}** envio(s) aguardando aprovação (de qualquer data). Eles ainda não entram nos valores.")
    secao = navegacao(["📱 Envios", "📉 Vales", "🏅 Premiações"], "nav_extrato")
    if secao == "📱 Envios":
        _envios(sb, coletas)
    elif secao == "📉 Vales":
        _vales(sb, vales)
    else:
        _premios(premios)
