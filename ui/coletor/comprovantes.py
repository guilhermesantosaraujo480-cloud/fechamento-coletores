"""Busca de comprovantes de clientes (por OS ou nome) e compartilhamento por WhatsApp."""
import urllib.parse

import streamlit as st

from core import sessao
from core.utils import data_br, limpar_termo_busca
from ui.componentes import cabecalho, cartao


def _registrar_busca(sb, termo, dados):
    """Grava uma vez por termo (não a cada rerun da página). Falha no log nunca atrapalha a busca."""
    if st.session_state.get("ultima_busca_registrada") == termo:
        return
    u = sessao.usuario_atual()
    try:
        sb.table("logs_comprovantes").insert({
            "usuario": u["usuario"], "nome_completo": u["nome_completo"], "termo_pesquisado": termo,
            "os_encontrada": ", ".join(str(r.get("ordem_servico", "")) for r in dados)[:500],
        }).execute()
        st.session_state["ultima_busca_registrada"] = termo
    except Exception:
        pass


def render(sb):
    cabecalho("🔍 Localizar comprovante do cliente", "Digite o número da OS ou o nome do cliente (mínimo 3 caracteres).")
    digitado = st.text_input("OS ou nome do cliente", placeholder="Ex.: 10542 ou Maria Silva").strip()
    termo = limpar_termo_busca(digitado)
    if digitado and len(termo) < 3:
        st.warning("Digite pelo menos 3 caracteres (sem símbolos) para buscar.")
        return
    if not termo:
        return
    try:
        dados = (sb.table("comprovantes_clientes").select("*")
                   .or_(f"cliente.ilike.%{termo}%,ordem_servico.ilike.%{termo}%")
                   .order("data_emissao", desc=True).limit(50).execute().data) or []
    except Exception as erro:
        st.error(f"Erro na base de dados: {erro}")
        return
    if not dados:
        st.info("ℹ️ Nenhum comprovante encontrado.")
        return
    _registrar_busca(sb, termo, dados)
    st.success(f"Encontrado(s) {len(dados)} item(ns)" + (" — mostrando os 50 mais recentes." if len(dados) == 50 else "."))
    colunas = st.columns(2)
    for i, reg in enumerate(dados):
        with colunas[i % 2]:
            with cartao():
                st.markdown(f"**📋 OS {reg.get('ordem_servico', '')}**")
                st.write(f"👤 {reg.get('cliente', '')}")
                st.caption(f"📅 Emissão: {data_br(reg.get('data_emissao'))}")
                url = reg.get("arquivo_url") or ""
                if url:
                    mensagem = (f"Olá! Segue o seu comprovante de coleta referente à *OS {reg.get('ordem_servico', '')}*."
                                f"\n\n🔗 Link:\n{url}")
                    b1, b2 = st.columns(2)
                    b1.link_button("📥 Abrir PDF", url, use_container_width=True)
                    b2.link_button("🟢 WhatsApp", f"https://api.whatsapp.com/send?text={urllib.parse.quote(mensagem)}",
                                   use_container_width=True)
                else:
                    st.caption("Sem arquivo anexado.")
