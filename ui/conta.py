"""Minha conta: trocar a própria senha."""
import streamlit as st

from core import auditoria, auth, sessao
from ui.componentes import cabecalho


def render(sb):
    u = sessao.usuario_atual()
    cabecalho("⚙️ Minha conta", f"{u['nome_completo']} · login `{u['usuario']}` · perfil {u['cargo']}")
    with st.form("form_senha", clear_on_submit=True):
        atual = st.text_input("Senha atual", type="password")
        nova = st.text_input(f"Nova senha (mínimo {auth.MIN_SENHA} caracteres)", type="password")
        repetir = st.text_input("Repita a nova senha", type="password")
        if st.form_submit_button("Alterar senha", type="primary"):
            if nova != repetir:
                st.error("As senhas novas não são iguais.")
            else:
                ok, msg = auth.alterar_propria_senha(sb, u["id"], atual, nova)
                (st.success if ok else st.error)(msg)
                if ok:
                    auditoria.registrar(sb, u["usuario"], "senha_alterada", "")
