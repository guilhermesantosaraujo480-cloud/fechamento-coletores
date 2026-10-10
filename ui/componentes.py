"""Peças de interface reutilizáveis."""
import streamlit as st

from core import dados
from core.exportacao import MIME_XLSX


def cartao():
    """Caixa com borda (cai para um container simples em versões antigas do Streamlit)."""
    try:
        return st.container(border=True)
    except TypeError:
        return st.container()


def cabecalho(titulo, subtitulo=""):
    st.markdown(f"### {titulo}")
    if subtitulo:
        st.caption(subtitulo)


def navegacao(opcoes, chave, local="topo"):
    """Menu de seções que só desenha a seção escolhida (st.tabs executa TODAS a cada clique)."""
    if local == "sidebar":
        return st.sidebar.radio("Menu", opcoes, key=chave, label_visibility="collapsed")
    if hasattr(st, "segmented_control"):
        escolha = st.segmented_control("Seção", opcoes, default=opcoes[0], key=chave, label_visibility="collapsed")
        return escolha or opcoes[0]
    return st.radio("Seção", opcoes, key=chave, horizontal=True, label_visibility="collapsed")


def metricas(itens):
    """itens: lista de (rótulo, valor) ou (rótulo, valor, ajuda) — uma coluna para cada."""
    colunas = st.columns(len(itens))
    for coluna, item in zip(colunas, itens):
        rotulo, valor = item[0], item[1]
        ajuda = item[2] if len(item) > 2 else None
        coluna.metric(rotulo, valor, help=ajuda)


def mostrar_foto(sb, valor, largura=None, legenda=None):
    url = dados.url_foto(sb, valor)
    if not url:
        st.caption("📷 Sem foto anexada")
        return
    if largura:
        st.image(url, width=largura, caption=legenda)
    else:
        st.image(url, use_container_width=True, caption=legenda)


def vazio(mensagem):
    st.info(mensagem)


def erro_banco(erro):
    st.error(f"Não foi possível falar com o banco de dados. Tente novamente em instantes.\n\nDetalhe técnico: {erro}")


def baixar_excel(rotulo, conteudo, nome_arquivo, chave=None):
    st.download_button(rotulo, data=conteudo, file_name=nome_arquivo, mime=MIME_XLSX,
                       use_container_width=True, key=chave)


def confirmar(rotulo, chave):
    """Caixa de confirmação para ações em massa. Devolve True se marcada."""
    return st.checkbox(rotulo, key=chave)
