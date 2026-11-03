"""Primeiro acesso com senha temporária (ou definida pelo administrador): o usuário precisa criar a própria senha antes de usar o sistema."""
import streamlit as st

from core import auditoria, auth, sessao


def render(sb, cookies):
    u = sessao.usuario_atual()
    _, centro, _ = st.columns([1, 1.4, 1])
    with centro:
        st.markdown("## Crie sua senha")
        st.info(f"Olá, {u['nome_completo']}. Você entrou com uma senha temporária. Crie agora a sua senha para continuar.")
        with st.form("form_troca_obrigatoria", clear_on_submit=True):
            nova = st.text_input(f"Nova senha (mínimo {auth.MIN_SENHA} caracteres)", type="password")
            repetir = st.text_input("Repita a nova senha", type="password")
            enviar = st.form_submit_button("Salvar e continuar", type="primary", use_container_width=True)
        if st.button("Sair", key="sair_troca"):
            sessao.sair(sb, cookies)
        if not enviar:
            return
        if nova != repetir:
            st.error("As senhas não são iguais.")
            return
        try:
            ok, msg = auth.concluir_troca_obrigatoria(sb, u["id"], nova)
        except Exception:
            st.error("Não foi possível salvar agora. Tente novamente em instantes.")
            return
        if not ok:
            st.error(msg)
            return
        try:
            auditoria.registrar(sb, u["usuario"], "senha_criada_primeiro_acesso", "")
        except Exception:  # noqa: BLE001 — o registro é secundário
            pass
        st.session_state["usuario"] = {**u, "trocar_senha": False}
        st.toast("Senha criada.", icon="✅")
        st.rerun()
