"""Gestão de usuários: cadastrar, redefinir senha, desativar e encerrar sessões."""
import re

import streamlit as st

from core import auditoria, auth, dados, sessao
from ui.componentes import cabecalho, cartao, erro_banco, vazio

PADRAO_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")


def _cadastrar(sb):
    usuario_adm = sessao.usuario_atual()["usuario"]
    with cartao():
        st.markdown("**➕ Novo usuário**")
        with st.form("form_novo_usuario", clear_on_submit=True):
            nome = st.text_input("Nome completo")
            login = st.text_input("Login de acesso", help="3 a 30 caracteres: letras minúsculas, números, ponto, hífen ou _").strip().lower()
            senha = st.text_input(f"Senha (mínimo {auth.MIN_SENHA} caracteres)", type="password")
            perfil = st.selectbox("Perfil", ["COLETOR", "ADM"])
            enviar = st.form_submit_button("Cadastrar", type="primary", use_container_width=True)
        if not enviar:
            return
        nome = nome.strip()
        if not (nome and login and senha):
            st.error("Preencha nome, login e senha.")
        elif not PADRAO_LOGIN.fullmatch(login):
            st.error("Login inválido: use 3 a 30 caracteres entre letras minúsculas, números, ponto, hífen ou _.")
        elif auth.validar_senha_nova(senha):
            st.error(auth.validar_senha_nova(senha))
        else:
            try:
                if sb.table("usuarios").select("id").eq("usuario", login).limit(1).execute().data:
                    st.error("Esse login já existe.")
                    return
                if perfil == "COLETOR" and sb.table("usuarios").select("id").eq("nome_completo", nome).limit(1).execute().data:
                    st.error("Já existe alguém com esse nome. Como as coletas são ligadas ao nome, use um nome diferente (ex.: com sobrenome).")
                    return
                sb.table("usuarios").insert({"usuario": login, "senha": auth.gerar_hash_senha(senha),
                                             "nome_completo": nome, "cargo": perfil}).execute()
                auditoria.registrar(sb, usuario_adm, "usuario_criado", f"{login} ({perfil})")
                dados.invalidar()
                st.toast(f"{nome} cadastrado.", icon="🎉")
                st.rerun()
            except Exception as erro:
                st.error(f"Erro ao cadastrar: {erro}")


def _gerenciar(sb, usuarios, tem_ativo):
    eu = sessao.usuario_atual()
    with cartao():
        st.markdown("**👥 Usuários cadastrados**")
        if not usuarios:
            vazio("Nenhum usuário.")
            return
        st.dataframe(
            [{"Nome": u["nome_completo"], "Login": u["usuario"], "Perfil": u["cargo"],
              "Situação": "🟢 Ativo" if u.get("ativo", True) else "🔴 Desativado"} for u in usuarios],
            hide_index=True, use_container_width=True)

        rotulos = {u["id"]: f"{u['nome_completo']} ({u['usuario']})" for u in usuarios}
        escolhido = st.selectbox("Gerenciar usuário", list(rotulos), format_func=rotulos.get,
                                 index=None, placeholder="Escolha um usuário...")
        if escolhido is None:
            return
        alvo = next(u for u in usuarios if u["id"] == escolhido)

        with st.form(f"form_reset_{escolhido}", clear_on_submit=True):
            nova = st.text_input("Nova senha para este usuário", type="password")
            if st.form_submit_button("🔑 Redefinir senha"):
                problema = auth.validar_senha_nova(nova)
                if problema:
                    st.error(problema)
                else:
                    auth.definir_senha(sb, escolhido, nova)
                    auditoria.registrar(sb, eu["usuario"], "senha_redefinida", alvo["usuario"])
                    st.success("Senha redefinida. O usuário foi desconectado.")

        c1, c2 = st.columns(2)
        if c1.button("🚪 Encerrar sessões", use_container_width=True, key=f"enc_{escolhido}"):
            auth.encerrar_sessao(sb, escolhido)
            auditoria.registrar(sb, eu["usuario"], "sessao_encerrada", alvo["usuario"])
            st.success("Sessão encerrada.")
        if tem_ativo:
            ativo = alvo.get("ativo", True)
            if alvo["usuario"] == eu["usuario"]:
                c2.caption("Você não pode desativar a si mesmo.")
            elif c2.button("🔴 Desativar" if ativo else "🟢 Reativar", use_container_width=True, key=f"ativ_{escolhido}"):
                sb.table("usuarios").update({"ativo": not ativo, **({} if not ativo else {"session_token": None})}).eq("id", escolhido).execute()
                auditoria.registrar(sb, eu["usuario"], "usuario_desativado" if ativo else "usuario_reativado", alvo["usuario"])
                dados.invalidar()
                st.rerun()
        else:
            c2.caption("Para desativar usuários, rode o `migracao_v2.sql`.")


def render(sb):
    try:
        usuarios, tem_ativo = dados.listar_usuarios(sb)
    except Exception as erro:
        erro_banco(erro)
        return
    cabecalho("👥 Usuários", "Cadastre pessoas, redefina senhas e desative quem saiu.")
    esquerda, direita = st.columns([2, 3])
    with esquerda:
        _cadastrar(sb)
    with direita:
        _gerenciar(sb, usuarios, tem_ativo)
