import streamlit as st
import pandas as pd
from datetime import datetime
import time
import uuid
import urllib.parse
from supabase import create_client, Client

# =========================================================================
# CONFIGURAÇÃO ESTILO APLICATIVO MÓVEL (MOBILE FIRST)
# =========================================================================
st.set_page_config(
    page_title="Meus Comprovantes", 
    layout="centered",               # Mantém o conteúdo centralizado igual app
    initial_sidebar_state="collapsed" # MARCAÇÃO CRUCIAL: Esconde a barra lateral por padrão
)

# CSS Otimizador para esconder menus nativos e deixar visual limpo de App
st.markdown("""
    <style>
        /* Esconde o botão de Deploy e o menu de 3 pontinhos do topo */
        #MainMenu, header {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Ajusta o espaçamento do topo para o conteúdo subir */
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 1rem;
        }
    </style>
""", unsafe_transform=True)

# ----------------- CONEXÃO COM O SUPABASE -----------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# ----------------- TRAVA DE SEGURANÇA / TELA DE LOGIN -----------------
if "logado" not in st.session_state or not st.session_state["logado"]:
    st.warning("🔒 Esta página é restrita. Por favor, faça o login para continuar.")
    
    user_input = st.text_input("Usuário (Login):", key="login_comprovantes").strip().lower()
    pass_input = st.text_input("Senha:", type="password", key="senha_comprovantes")
    
    if st.button("Entrar", type="primary", use_container_width=True):
        try:
            resposta = supabase.table("usuarios").select("*").eq("usuario", user_input).eq("senha", str(pass_input)).execute()
            user_valido = resposta.data
            
            if user_valido:
                novo_token = str(uuid.uuid4())
                supabase.table("usuarios").update({"session_token": novo_token}).eq("id", user_valido[0]["id"]).execute()
                
                st.session_state["logado"] = True
                st.session_state["usuario_atual"] = user_input
                st.session_state["nome_completo_atual"] = user_valido[0]["nome_completo"]
                st.session_state["cargo_atual"] = user_valido[0]["cargo"]
                st.query_params["session"] = novo_token
                
                st.success(f"🔓 Acesso liberado! Bem-vindo, {st.session_state['nome_completo_atual']}.")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
        except Exception as e:
            st.error(f"Erro ao conectar com o banco de dados: {e}")
            
    st.stop()

# =========================================================================
# SE CHEGOU AQUI, SIGNIFICA QUE ESTÁ LOGADO
# =========================================================================

if st.session_state["cargo_atual"] == "ADM":
    st.info("🛡️ Olá, Administrador! Modo de visualização de testes ativado.")

st.title("📄 Comprovantes de Coleta")
st.write(f"👤 Coletor: **{st.session_state['nome_completo_atual']}**")
st.markdown("---")

# Botão de Sair em formato menor, alinhado à direita
col_vazia, col_sair = st.columns([2, 1])
with col_sair:
    if st.button("🚪 Sair do App", use_container_width=True):
        try:
            supabase.table("usuarios").update({"session_token": None}).eq("usuario", st.session_state["usuario_atual"]).execute()
        except:
            pass
        st.query_params.clear()
        st.session_state["logado"] = False
        st.session_state["usuario_atual"] = None
        st.session_state["nome_completo_atual"] = None
        st.session_state["cargo_atual"] = None
        st.rerun()

st.subheader("🔍 Localizar Comprovante")
termo_busca = st.text_input("Digite a OS ou Nome do Cliente:", placeholder="Ex: 10542...").strip()

if termo_busca:
    try:
        resposta = supabase.table("comprovantes_clientes").select("*").or_(f"cliente.ilike.%{termo_busca}%,ordem_servico.ilike.%{termo_busca}%").order("data_emissao", ascending=False).execute()
        dados = resposta.data
        
        if not dados:
            st.info("ℹ️ Nenhum comprovante encontrado.")
        else:
            st.success(f"🎉 Encontrado(s) {len(dados)} item(ns):")
            
            for registro in dados:
                with st.container():
                    st.markdown(f"### 📋 OS: {registro['ordem_servico']}")
                    st.markdown(f"**👤 Cliente:** {registro['cliente']}")
                    
                    data_formatada = datetime.strptime(registro['data_emissao'], '%Y-%m-%d').strftime('%d/%m/%Y')
                    st.markdown(f"**📅 Emissão:** {data_formatada}")
                    
                    url_comprovante = registro['arquivo_url']
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        st.link_button("📥 Abrir PDF", url_comprovante, use_container_width=True)
                        
                    with col_btn2:
                        mensagem_zap = (
                            f"Olá! Segue o seu comprovante de coleta referente à *OS {registro['ordem_servico']}*.\n\n"
                            f"🔗 Para visualizar e baixar o documento, clique no link abaixo:\n"
                            f"{url_comprovante}"
                        )
                        mensagem_codificada = urllib.parse.quote(mensagem_zap)
                        link_whatsapp = f"https://api.whatsapp.com/send?text={mensagem_codificada}"
                        
                        st.link_button("🟢 Enviar WhatsApp", link_whatsapp, use_container_width=True)
                st.markdown("---")
    except Exception as e:
        st.error(f"Erro na base de dados: {e}")
else:
    st.info("💡 Digite os dados acima para pesquisar.")