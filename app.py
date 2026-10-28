"""Sistema Vivo Coletas — ponto de entrada. Só monta a página e escolhe qual módulo desenhar."""
import streamlit as st

st.set_page_config(page_title="Sistema Vivo Coletas", page_icon="📱", layout="wide", initial_sidebar_state="auto")

import importlib  # noqa: E402
import time as _time  # noqa: E402

try:  # versões novas do Streamlit: traduz use_container_width -> width (nada muda se a versão ainda aceita)
    from core import compat as _compat  # noqa: E402
    _compat.instalar(st)
except Exception:  # noqa: BLE001 — compatibilidade nunca pode derrubar o app
    pass

from streamlit_cookies_controller import CookieController  # noqa: E402

from core import dados, sessao  # noqa: E402
from core.db import get_supabase  # noqa: E402
from ui import estilos, login  # noqa: E402
from ui.adm.filtros import filtros_sidebar  # noqa: E402
from ui.componentes import navegacao  # noqa: E402

# página -> (módulo, usa os filtros de período/coletor da barra lateral?)
# Os módulos só são carregados quando a página é aberta: o coletor não gasta memória/tempo com as telas do
# administrador (rotas, disparador, bipagem...), e o administrador só carrega a tela que está usando.
PAGINAS_ADM = {
    "📊 Visão geral": ("ui.adm.visao_geral", True),
    "📋 Coletas": ("ui.adm.coletas", True),
    "💵 Fechamento": ("ui.adm.fechamento", True),
    "📉 Vales": ("ui.adm.vales", True),
    "🏅 Premiações": ("ui.adm.premiacoes", True),
    "🚚 Rotas": ("ui.adm.rotas", False),
    "🔖 Bipagem": ("ui.adm.bipagem", False),
    "👥 Usuários": ("ui.adm.usuarios", False),
    "📧 E-mails": ("ui.adm.emails", False),
    "🛡️ Auditoria": ("ui.adm.auditoria", False),
    "⚙️ Minha conta": ("ui.conta", False),
}
PAGINAS_COLETOR = {
    "📲 Enviar coleta": "ui.coletor.enviar",
    "📊 Meu extrato": "ui.coletor.extrato",
    "🔍 Comprovantes": "ui.coletor.comprovantes",
    "⚙️ Minha conta": "ui.conta",
}


def _desenhar(modulo):
    return importlib.import_module(modulo).render


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
    modulo, usa_filtro = PAGINAS_ADM[pagina]
    funcao = _desenhar(modulo)
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
    _desenhar(PAGINAS_COLETOR[pagina])(sb)


def _marcador():
    """Diagnóstico: abra o site com ?debug=1 no fim do endereço e cada etapa da abertura aparece na tela
    (se o site ficar em branco, a última linha mostra onde parou)."""
    if st.query_params.get("debug") != "1":
        return lambda texto: None
    inicio = _time.perf_counter()
    st.caption(f"🔧 Streamlit {getattr(st, '__version__', '?')} — para travar nesta versão, use `streamlit=={getattr(st, '__version__', '?')}` no requirements.txt")
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
