"""Sistema Vivo Coletas — ponto de entrada. Só monta a página e escolhe qual módulo desenhar."""
import streamlit as st

st.set_page_config(page_title="Sistema Vivo Coletas", page_icon="📱", layout="wide", initial_sidebar_state="auto")

from streamlit_cookies_controller import CookieController  # noqa: E402

from core import dados, sessao  # noqa: E402
from core.db import get_supabase  # noqa: E402
from ui import conta, estilos, login  # noqa: E402
from ui.adm import auditoria, coletas, emails, fechamento, premiacoes, usuarios, vales, visao_geral  # noqa: E402
from ui.adm.filtros import filtros_sidebar  # noqa: E402
from ui.componentes import navegacao  # noqa: E402
from ui.coletor import comprovantes, enviar, extrato  # noqa: E402

# página -> (função, usa os filtros de período/coletor da barra lateral?)
PAGINAS_ADM = {
    "📊 Visão geral": (visao_geral.render, True),
    "📋 Coletas": (coletas.render, True),
    "💵 Fechamento": (fechamento.render, True),
    "📉 Vales": (vales.render, True),
    "🏅 Premiações": (premiacoes.render, True),
    "👥 Usuários": (usuarios.render, False),
    "📧 E-mails": (emails.render, False),
    "🛡️ Auditoria": (auditoria.render, False),
    "⚙️ Minha conta": (conta.render, False),
}
PAGINAS_COLETOR = {
    "📲 Enviar coleta": enviar.render,
    "📊 Meu extrato": extrato.render,
    "🔍 Comprovantes": comprovantes.render,
    "⚙️ Minha conta": conta.render,
}


def barra_superior(sb, cookies):
    u = sessao.usuario_atual()
    titulo, sair = st.columns([5, 1])
    titulo.markdown(f"**📱 Sistema de Coletas** &nbsp;·&nbsp; 👤 {u['nome_completo']} ({u['cargo']})")
    if sair.button("Sair", use_container_width=True):
        sessao.sair(sb, cookies)


def area_adm(sb):
    try:
        pendentes = dados.contar_pendentes(sb)
    except Exception:
        pendentes = 0
    with st.sidebar:
        st.markdown("##### 🛡️ Painel do administrador")
        if pendentes:
            st.warning(f"⏳ {pendentes} coleta(s) para aprovar")
    pagina = navegacao(list(PAGINAS_ADM), "nav_adm", local="sidebar")
    funcao, usa_filtro = PAGINAS_ADM[pagina]
    if usa_filtro:
        try:
            coletores = dados.nomes_coletores(sb, somente_ativos=False)
        except Exception:
            coletores = []
        funcao(sb, filtros_sidebar(coletores))
    else:
        funcao(sb)


def area_coletor(sb):
    pagina = navegacao(list(PAGINAS_COLETOR), "nav_coletor")
    PAGINAS_COLETOR[pagina](sb)


def main():
    estilos.aplicar()
    sb = get_supabase()
    cookies = CookieController()
    if "session" in st.query_params:  # links antigos carregavam o token na URL
        del st.query_params["session"]

    sessao.restaurar(sb, cookies)
    if not sessao.usuario_atual():
        login.render(sb, cookies)
        return
    sessao.revalidar(sb, cookies)
    barra_superior(sb, cookies)
    (area_adm if sessao.eh_adm() else area_coletor)(sb)


main()
