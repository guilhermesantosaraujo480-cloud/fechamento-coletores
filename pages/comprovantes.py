import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client
import urllib.parse

# Configuração da Página (focada em mobile)
st.set_page_config(page_title="Meus Comprovantes", layout="centered", initial_sidebar_state="collapsed")

# ----------------- CONEXÃO COM O SUPABASE -----------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

st.title("📄 Meus Comprovantes de Coleta")
st.markdown("Busque os comprovantes dos seus clientes para enviar diretamente a eles.")

# ----------------- CONTROLE DE ACESSO -----------------
if "logado" not in st.session_state or not st.session_state["logado"]:
    st.warning("⚠️ Por favor, faça login na página principal primeiro.")
    st.stop()

# =========================================================================
# ÁREA DE BUSCA DO COLETOR
# =========================================================================
st.subheader("🔍 Localizar Comprovante")

# Campo de busca único por Cliente ou OS
termo_busca = st.text_input("Digite o Nome do Cliente ou o Número da OS:", placeholder="Ex: 10542 ou João Silva").strip()

if termo_busca:
    try:
        # Busca na tabela do banco se o termo bate com cliente OU ordem de serviço
        resposta = supabase.table("comprovantes_clientes").select("*").or_(f"cliente.ilike.%{termo_busca}%,ordem_servico.ilike.%{termo_busca}%").order("data_emissao", ascending=False).execute()
        dados = resposta.data
        
        if not dados:
            st.info("ℹ️ Nenhum comprovante encontrado para este termo. Verifique se digitou corretamente.")
        else:
            st.success(f"🎉 Encontrado(s) {len(dados)} comprovante(s):")
            
            for registro in dados:
                with st.container():
                    st.markdown(f"### 📋 OS: {registro['ordem_servico']}")
                    st.markdown(f"**👤 Cliente:** {registro['cliente']}")
                    
                    # Formata a data para o padrão brasileiro
                    data_formatada = datetime.strptime(registro['data_emissao'], '%Y-%m-%d').strftime('%d/%m/%Y')
                    st.markdown(f"**📅 Emissão:** {data_formatada}")
                    
                    url_comprovante = registro['arquivo_url']
                    
                    # Botões lado a lado otimizados para celular
                    col_btn1, col_btn2 = st.columns(2)
                    
                    with col_btn1:
                        # Abre o PDF direto no navegador do celular
                        st.link_button("📥 Abrir PDF", url_comprovante, use_container_width=True)
                        
                    with col_btn2:
                        # Texto padrão que o coletor vai disparar para o cliente dele no WhatsApp
                        mensagem_zap = (
                            f"Olá! Segue o seu comprovante de coleta referente à *OS {registro['ordem_servico']}*.\n\n"
                            f"🔗 Para visualizar e baixar o documento, clique no link abaixo:\n"
                            f"{url_comprovante}"
                        )
                        mensagem_codificada = urllib.parse.quote(mensagem_zap)
                        link_whatsapp = f"https://api.whatsapp.com/send?text={mensagem_codificada}"
                        
                        st.link_button("🟢 Enviar no Whats", link_whatsapp, use_container_width=True)
                        
                st.markdown("---")
    except Exception as e:
        st.error(f"Erro ao conectar na base de dados: {e}")
else:
    st.info("💡 Digite o número da OS ou o nome do cliente acima para pesquisar.")