"""Sessão do usuário: estado do Streamlit + cookie com token (o banco guarda só o hash)."""
import time

import streamlit as st

from . import auth

COOKIE = "vivo_coletas_session"
DURACAO_COOKIE_SEG = 14 * 24 * 3600


@st.cache_resource
def limitador():
    """Compartilhado entre todas as sessões do servidor."""
    return auth.Limitador(max_falhas=5, janela_seg=300)


def usuario_atual():
    return st.session_state.get("usuario")


def eh_adm():
    u = usuario_atual()
    return bool(u) and u.get("cargo") == "ADM"


def restaurar(sb, cookies):
    """Reabre a sessão a partir do cookie (se existir e ainda for válido)."""
    if usuario_atual():
        return
    token = cookies.get(COOKIE)
    if not token:
        return
    try:
        usuario = auth.usuario_por_token(sb, token)
    except Exception:
        return
    if usuario:
        st.session_state["usuario"] = usuario


def entrar(resultado, cookies, lembrar):
    st.session_state["usuario"] = resultado.usuario
    if lembrar:
        cookies.set(COOKIE, resultado.token, max_age=DURACAO_COOKIE_SEG)
    time.sleep(0.3)  # dá tempo do cookie ser gravado antes do rerun


def sair(sb, cookies):
    u = usuario_atual()
    try:
        if u:
            auth.encerrar_sessao(sb, u["id"])
        cookies.remove(COOKIE)
    except Exception:
        pass
    for chave in list(st.session_state.keys()):
        del st.session_state[chave]
    st.rerun()


def revalidar(sb, cookies, intervalo_seg=300):
    """De tempos em tempos confere se o usuário continua existindo/ativo (e se o perfil não mudou)."""
    u = usuario_atual()
    if not u or time.time() - st.session_state.get("_revalidado", 0) < intervalo_seg:
        return
    st.session_state["_revalidado"] = time.time()
    try:
        linhas = sb.table("usuarios").select("*").eq("id", u["id"]).limit(1).execute().data
    except Exception:
        return  # falha de rede não derruba ninguém
    if not linhas or linhas[0].get("ativo") is False:
        sair(sb, cookies)
    elif linhas[0].get("cargo") != u["cargo"]:
        st.session_state["usuario"] = auth.dados_publicos(linhas[0])
