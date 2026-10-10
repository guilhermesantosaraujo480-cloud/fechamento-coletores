"""Conexão única com o Supabase (reaproveitada entre as sessões)."""
import streamlit as st


@st.cache_resource(show_spinner=False)
def _criar_cliente(url, chave):
    from supabase import create_client

    return create_client(url, chave)


def get_supabase():
    """Devolve o cliente. Se faltar configuração, mostra uma mensagem clara em vez de um erro técnico."""
    try:
        url, chave = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    except Exception:
        st.error("Faltam `SUPABASE_URL` e `SUPABASE_KEY` nos secrets do app (Settings → Secrets).")
        st.stop()
    try:
        return _criar_cliente(url, chave)
    except Exception as erro:
        st.error(f"Não foi possível iniciar a conexão com o banco: {erro}")
        st.stop()
