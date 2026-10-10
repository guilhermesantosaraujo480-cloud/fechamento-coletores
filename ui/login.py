"""Tela de login."""
import streamlit as st

from core import auth, sessao


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
        if not enviar:
            return
        try:
            resultado = auth.autenticar(sb, usuario, senha, sessao.limitador())
        except Exception as erro:
            st.error(f"Erro ao conectar com o banco de dados: {erro}")
            return
        if not resultado.ok:
            st.error(resultado.mensagem)
            return
        sessao.entrar(resultado, cookies, lembrar)
        st.rerun()
