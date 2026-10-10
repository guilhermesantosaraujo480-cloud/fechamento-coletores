"""Auditoria: ações administrativas e buscas de comprovantes feitas pelos coletores."""
import pandas as pd
import streamlit as st

from core import auditoria
from core.utils import serie_utc_para_br
from ui.componentes import cabecalho, navegacao, vazio


def _acoes(sb):
    try:
        linhas = auditoria.listar(sb, 300)
    except Exception:
        st.info("A trilha de auditoria ainda não foi criada. Rode o `migracao_v2.sql` no Supabase.")
        return
    if not linhas:
        vazio("Nenhuma ação registrada ainda.")
        return
    df = pd.DataFrame(linhas)
    df["Horário"] = serie_utc_para_br(df["data_hora"])
    busca = st.text_input("Filtrar por usuário, ação ou detalhe", key="aud_busca").strip().lower()
    if busca:
        mascara = (df[["usuario", "acao", "detalhe"]].astype(str).apply(lambda c: c.str.lower().str.contains(busca, regex=False))).any(axis=1)
        df = df[mascara]
    st.dataframe(df[["Horário", "usuario", "acao", "detalhe"]].rename(
        columns={"usuario": "Quem", "acao": "Ação", "detalhe": "Detalhe"}), hide_index=True, use_container_width=True)


def _buscas(sb):
    try:
        linhas = sb.table("logs_comprovantes").select("*").order("data_hora", desc=True).limit(300).execute().data
    except Exception as erro:
        st.error(f"Erro ao carregar o relatório: {erro}")
        return
    if not linhas:
        vazio("Nenhuma busca registrada até o momento.")
        return
    df = pd.DataFrame(linhas)
    df["Horário"] = serie_utc_para_br(df["data_hora"])
    st.dataframe(df[["Horário", "nome_completo", "termo_pesquisado", "os_encontrada"]].rename(columns={
        "nome_completo": "Coletor", "termo_pesquisado": "Termo buscado", "os_encontrada": "OS encontrada(s)"}),
        hide_index=True, use_container_width=True)


def render(sb):
    cabecalho("🛡️ Auditoria", "Quem fez o quê no sistema.")
    secao = navegacao(["Ações no sistema", "Buscas de comprovantes"], "nav_auditoria")
    (_acoes if secao == "Ações no sistema" else _buscas)(sb)
