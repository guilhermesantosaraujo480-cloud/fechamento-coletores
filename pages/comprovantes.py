import streamlit as st
import pandas as pd
from datetime import datetime
import time
import uuid
import urllib.parse
from supabase import create_client, Client

# Configuração da Página (focada em mobile)
st.set_page_config(page_title="Meus Comprovantes", layout="centered", initial_sidebar_state="collapsed")

# ----------------- CONEXÃO COM O SUPABASE -----------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# ----------------- TRAVA DE SEGURANÇA / TELA DE LOGIN -----------------
# Se o usuário não veio logado do app.py, exigimos o login aqui dentro também
if "logado" not in st.session_state or not st.session_state["logado"]:
    st.warning("🔒 Esta página é restrita. Por favor, faça o login para continuar.")
    
    user_input = st.text_input("Usuário (Login):", key="login_comprovantes").strip().lower()
    pass_input = st.text_input("Senha:", type="password", key="senha_comprovantes")
    
    if st.button("Entrar", type="primary", use_container_width=True):
        try:
            resposta = supabase.table("usuarios").select("*").eq("usuario", user_input).eq("senha", str(pass_input)).execute()
            user_valido = resposta.data
            
            if user_valido:
                # Se for ADM, podemos escolher bloquear ou deixar passar (aqui deixei passar se você quiser fiscalizar)
                novo_token = str(uuid.uuid4())
                supabase.table("usuarios").update({"session_token": novo_token}).eq("id", user_valido[0]["id"]).execute()
                
                # Salva o estado de login global do sistema
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
            
    # Trava a execução do restante do código caso não esteja logado
    st.stop()


# =========================================================================
# SE CHEGOU AQUI, SIGNIFICA QUE ESTÁ LOGADO (O CÓDIGO DA BUSCA RODA ABAIXO)
# =========================================================================

# Se o usuário logado for um ADM e você quiser que apenas COLETORES usem essa página:
if st.session_state["cargo_atual"] == "ADM":
    st.info("🛡️ Olá, Administrador! Esta página é destinada aos coletores, mas você pode visualizar e testar o funcionamento abaixo.")

st.title("📄 Meus Comprovantes de Coleta")
st.write(f"👤 Coletor: **{st.session_state['nome_completo_atual']}**")
st.markdown("---")

# Botão de Sair rápido
if st.button("🚪 Sair do Sistema", use_container_width=False):
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

# Campo de busca único por Cliente ou OS
termo_busca = st.text_input("Digite o Nome do Cliente ou o Número da OS:", placeholder="Ex: 10542 ou João Silva").strip()

if termo_busca:
    try:
        resposta = supabase.table("comprovantes_clientes").select("*").or_(f"cliente.ilike.%{termo_busca}%,ordem_servico.ilike.%{termo_busca}%").order("data_emissao", ascending=False).execute()
        dados = resposta.data
        
        if not dados:
            st.info("ℹ️ Nenhum comprovante encontrado para este termo.")
        else:
            st.success(f"🎉 Encontrado(s) {len(dados)} comprovante(s):")
            
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
                        
                        st.link_button("🟢 Enviar no Whats", link_whatsapp, use_container_width=True)
                st.markdown("---")
    except Exception as e:
        st.error(f"Erro ao conectar na base de dados: {e}")
else:
    st.info("💡 Digite o número da OS ou o nome do cliente acima para pesquisar.")