"""Tela de login."""
import streamlit as st

from core import auth, sessao


MAX_PEDIDOS_POR_SESSAO = 3


def _esqueci(sb):
    with st.expander("Esqueci a senha"):
        st.caption("Informe seu usuário. O administrador vai gerar uma senha temporária e avisar você.")
        with st.form("form_esqueci", clear_on_submit=True):
            login = st.text_input("Seu usuário", key="esqueci_usuario")
            pedir = st.form_submit_button("Pedir nova senha", use_container_width=True)
        if not pedir:
            return
        if st.session_state.get("pedidos_senha_feitos", 0) >= MAX_PEDIDOS_POR_SESSAO:
            st.warning("Você já fez alguns pedidos. Fale diretamente com o administrador.")
            return
        st.session_state["pedidos_senha_feitos"] = st.session_state.get("pedidos_senha_feitos", 0) + 1
        try:
            auth.pedir_redefinicao(sb, login)
        except Exception:
            st.error("Não foi possível enviar o pedido agora. Tente novamente em instantes ou fale com o administrador.")
            return
        st.success(auth.MENSAGEM_PEDIDO)  # mesma resposta exista o login ou não


def render(sb, cookies):
    _, centro, _ = st.columns([1, 1.4, 1])
    with centro:
        st.markdown("## 📱 Sistema de Coletas")
        st.caption("Entre com seu usuário e senha.")
        with st.form("form_login"):  # Enter envia o formulário
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            lembrar = st.checkbox("Manter-me conectado neste aparelho", value=True)
            enviar = st.form_submit_button("Entrar", type="primary", use_container_width=True)
        _esqueci(sb)
        if not enviar:
            return
        try:
            resultado = auth.autenticar(sb, usuario, senha, sessao.limitador())
        except Exception as erro:
            st.error("Não foi possível entrar agora. Tente novamente em instantes.")
            return
        if not resultado.ok:
            st.error(resultado.mensagem)
            return
        sessao.entrar(resultado, cookies, lembrar)
        st.rerun()
