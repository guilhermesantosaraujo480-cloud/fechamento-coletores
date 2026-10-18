"""Sistema Vivo Coletas — ponto de entrada. Só monta a página e escolhe qual módulo desenhar."""
import streamlit as st

st.set_page_config(page_title="Sistema Vivo Coletas", page_icon="📱", layout="wide", initial_sidebar_state="auto")

import time as _time  # noqa: E402

from streamlit_cookies_controller import CookieController  # noqa: E402

from core import dados, sessao  # noqa: E402
from core.db import get_supabase  # noqa: E402
from ui import conta, estilos, login  # noqa: E402
from ui.adm import auditoria, bipagem, coletas, emails, fechamento, premiacoes, rotas, usuarios, vales, visao_geral  # noqa: E402
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
    "🚚 Rotas": (rotas.render, False),
    "🔖 Bipagem": (bipagem.render, False),
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


def _marcador():
    """Diagnóstico: abra o site com ?debug=1 no fim do endereço e cada etapa da abertura aparece na tela
    (se o site ficar em branco, a última linha mostra onde parou)."""
    if st.query_params.get("debug") != "1":
        return lambda texto: None
    inicio = _time.perf_counter()
    return lambda texto: st.caption(f"🔧 {_time.perf_counter() - inicio:5.1f}s · {texto}")


def main():
    marca = _marcador()
    marca("1/6 início")
    estilos.aplicar()
    sb = get_supabase()
    marca("2/6 banco de dados conectado")
    cookies = CookieController()
    marca("3/6 cookies carregados")
    if "session" in st.query_params:  # links antigos carregavam o token na URL
        del st.query_params["session"]

    sessao.restaurar(sb, cookies)
    marca("4/6 sessão verificada")
    if not sessao.usuario_atual():
        marca("5/6 mostrando o login")
        login.render(sb, cookies)
        return
    sessao.revalidar(sb, cookies)
    barra_superior(sb, cookies)
    marca(f"5/6 logado como {sessao.usuario_atual().get('cargo')}; desenhando a página")
    (area_adm if sessao.eh_adm() else area_coletor)(sb)
    marca("6/6 página desenhada")


main()
