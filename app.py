import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# Configuração da página (otimizada para celular)
st.set_page_config(page_title="Sistema Vivo Coletas", layout="centered", initial_sidebar_state="collapsed")

# VALOR PADRÃO POR COLETA
VALOR_POR_COLETA = 10.0

# ----------------- CONEXÃO COM O BANCO DE DADOS (SUPABASE) -----------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# ----------------- SESSÃO DE LOGIN E FILTROS -----------------
if "logado" not in st.session_state:
    st.session_state["logado"] = False
    st.session_state["usuario_atual"] = None
    st.session_state["nome_completo_atual"] = None
    st.session_state["cargo_atual"] = None

# Contador para limpar campos de inputs de forma limpa
if "reset_ctr" not in st.session_state:
    st.session_state["reset_ctr"] = 0

# Estados dos filtros do ADM
if "filtro_data_inicio" not in st.session_state:
    st.session_state["filtro_data_inicio"] = datetime.now().date()
if "filtro_data_fim" not in st.session_state:
    st.session_state["filtro_data_fim"] = datetime.now().date()
if "filtro_coletor" not in st.session_state:
    st.session_state["filtro_coletor"] = "Todos"

# Estados dos filtros do COLETOR
if "c_filtro_inicio" not in st.session_state:
    st.session_state["c_filtro_inicio"] = datetime.now().date()
if "c_filtro_fim" not in st.session_state:
    st.session_state["c_filtro_fim"] = datetime.now().date()

# TÍTULO PRINCIPAL
st.title("📱 Sistema de Coletas")
st.markdown("---")

# ----------------- TELA DE LOGIN -----------------
if not st.session_state["logado"]:
    st.subheader("🔑 Acesso ao Sistema")
    user_input = st.text_input("Usuário (Login):").strip().lower()
    pass_input = st.text_input("Senha:", type="password")
    
    if st.button("Entrar", type="primary", use_container_width=True):
        try:
            resposta = supabase.table("usuarios").select("*").eq("usuario", user_input).eq("senha", str(pass_input)).execute()
            user_valido = resposta.data
            
            if user_valido:
                st.session_state["logado"] = True
                st.session_state["usuario_atual"] = user_input
                st.session_state["nome_completo_atual"] = user_valido[0]["nome_completo"]
                st.session_state["cargo_atual"] = user_valido[0]["cargo"]
                st.success(f"Bem-vindo, {st.session_state['nome_completo_atual']}!")
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
        except Exception as e:
            st.error(f"Erro ao conectar com o banco de dados: {e}")

# ----------------- ÁREA DO SISTEMA (APÓS LOGIN) -----------------
else:
    col_user, col_logout = st.columns([3, 1])
    col_user.write(f"👤 Conectado: **{st.session_state['nome_completo_atual']}** ({st.session_state['cargo_atual']})")
    if col_logout.button("Sair", use_container_width=True):
        st.session_state["logado"] = False
        st.rerun()

    # =========================================================================
    # PERFIL ADMINISTRADOR
    # =========================================================================
    if st.session_state["cargo_atual"] == "ADM":
        st.subheader("🛡️ Painel do Administrador")
        sub_menu_adm = st.tabs(["📋 Gestão de Coletas", "📉 Registrar/Ver Vales", "👤 Cadastrar Usuários"])
        
        # --- 1. GESTÃO DE COLETAS E FILTROS ---
        with sub_menu_adm[0]:
            try:
                res_coletas = supabase.table("coletas").select("*").execute()
                res_users = supabase.table("usuarios").select("*").execute()
                
                df = pd.DataFrame(res_coletas.data) if res_coletas.data else pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
                
                res_users_data = res_users.data if res_users.data else []
                lista_coletores = ["Todos"] + [u["nome_completo"] for u in res_users_data if u.get("cargo") == "COLETOR"]
            except Exception as e:
                st.error(f"Erro ao carregar dados do banco: {e}")
                df = pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
                lista_coletores = ["Todos"]
            
            st.subheader("🔍 Filtros de Busca")
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                data_inicio = st.date_input("Data Início:", value=st.session_state["filtro_data_inicio"])
            with col_f2:
                data_fim = st.date_input("Data Fim:", value=st.session_state["filtro_data_fim"])
            with col_f3:
                coletor_sel = st.selectbox("Filtrar por Coletor:", lista_coletores, index=lista_coletores.index(st.session_state["filtro_coletor"]) if st.session_state["filtro_coletor"] in lista_coletores else 0)
            
            st.session_state["filtro_data_inicio"] = data_inicio
            st.session_state["filtro_data_fim"] = data_fim
            st.session_state["filtro_coletor"] = coletor_sel

            if st.button("❌ Limpar Filtros", use_container_width=True):
                st.session_state["filtro_data_inicio"] = datetime.now().date()
                st.session_state["filtro_data_fim"] = datetime.now().date()
                st.session_state["filtro_coletor"] = "Todos"
                st.rerun()
            
            if not df.empty:
                df['data_dt'] = pd.to_datetime(df['data'])
                df_filtrado = df[(df['data_dt'] >= pd.to_datetime(data_inicio)) & (df['data_dt'] <= pd.to_datetime(data_fim))]
                if coletor_sel != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["coletor"] == coletor_sel]
            else:
                df_filtrado = df
            
            # --- SEÇÃO DE APROVAÇÕES ---
            st.subheader("📥 Coletas Pendentes no Período")
            pendentes = df_filtrado[df_filtrado["status"] == "Pendente"] if not df_filtrado.empty else pd.DataFrame()
            if pendentes.empty:
                st.info("Nenhuma coleta pendente encontrada.")
            else:
                for index, row in pendentes.iterrows():
                    col1, col2 = st.columns([3, 2])
                    with col1:
                        st.write(f"**Coletor:** {row['coletor']} | **Qtd:** {row['quantidade']} un")
                        link_foto = row.get('foto_url')
                        if link_foto: st.image(link_foto, width=150)
                    with col2:
                        if st.button(f"✓ Aprovar", key=f"ap_{row['id']}", type="primary"):
                            supabase.table("coletas").update({"status": "Aprovado"}).eq("id", row["id"]).execute()
                            st.rerun()
                        if st.button(f"✕ Recusar", key=f"rec_{row['id']}"):
                            supabase.table("coletas").update({"status": "Recusado"}).eq("id", row["id"]).execute()
                            st.rerun()
                    st.markdown("---")
            
            # --- SEÇÃO DE FECHAMENTO FINANCEIRO ---
            st.subheader("💵 Fechamento Financeiro")
            
            try:
                res_vales = supabase.table("vales_coleta").select("*").execute()
                df_vales = pd.DataFrame(res_vales.data) if res_vales.data else pd.DataFrame(columns=["id", "data", "coletor", "valor_vale", "descricao"])
            except Exception:
                df_vales = pd.DataFrame(columns=["id", "data", "coletor", "valor_vale", "descricao"])
                
            if not df_vales.empty:
                df_vales['data_dt'] = pd.to_datetime(df_vales['data'])
                vales_filtrados = df_vales[(df_vales['data_dt'] >= pd.to_datetime(data_inicio)) & (df_vales['data_dt'] <= pd.to_datetime(data_fim))]
                if coletor_sel != "Todos":
                    vales_filtrados = vales_filtrados[vales_filtrados["coletor"] == coletor_sel]
                total_vales = vales_filtrados["valor_vale"].sum()
            else:
                total_vales = 0.0
            
            aprovados_periodo = df_filtrado[df_filtrado["status"] == "Aprovado"] if not df_filtrado.empty else pd.DataFrame()
            
            if not aprovados_periodo.empty:
                total_bruto = aprovados_periodo["valor_total"].sum()
                total_nao_pago_adm = aprovados_periodo[aprovados_periodo["pago"] != "Sim"]["valor_total"].sum()
            else:
                total_bruto = 0.0
                total_nao_pago_adm = 0.0
            
            total_liquido = max(0.0, float(total_nao_pago_adm) - float(total_vales))
            
            cm1, cm2, cm3 = st.columns(3)
            cm1.metric("Bruto Aprovado", f"R$ {total_bruto:.2f}")
            cm2.metric("Desconto em Vales (-)", f"R$ {total_vales:.2f}")
            cm3.metric("Líquido a Pagar", f"R$ {total_liquido:.2f}")
            
            st.markdown("#### Detalhes dos Aprovados")
            if aprovados_periodo.empty:
                st.info("Nenhuma coleta aprovada neste período.")
            else:
                for index, row in aprovados_periodo.iterrows():
                    pago_atual = row.get('pago', 'Não')
                    status_pago_txt = "✅ Já Pago" if pago_atual == "Sim" else "❌ Não Pago"
                    
                    col_p1, col_p2 = st.columns([3, 2])
                    with col_p1:
                        st.write(f"**{row['coletor']}** | R$ {float(row['valor_total']):.2f} | Data: {row['data']} ({status_pago_txt})")
                    with col_p2:
                        if pago_atual != "Sim":
                            if st.button(f"Marcar como Pago", key=f"pag_{row['id']}"):
                                supabase.table("coletas").update({"pago": "Sim"}).eq("id", row["id"]).execute()
                                st.rerun()
                    st.markdown("---")

        # --- 2. ABA DE VALES (ADMIN) ---
        with sub_menu_adm[1]:
            st.subheader("💰 Registrar Vale / Adiantamento")
            try:
                res_users = supabase.table("usuarios").select("*").execute()
                res_users_data = res_users.data if res_users.data else []
                coletores_vales = [u["nome_completo"] for u in res_users_data if u.get("cargo") == "COLETOR"]
            except Exception:
                coletores_vales = []
            
            if coletores_vales:
                coletor_vale = st.selectbox("Selecione o Coletor para o Vale:", coletores_vales, key=f"sel_vale_{st.session_state['reset_ctr']}")
                valor_vale_input = st.number_input("Valor do Adiantamento (R$):", min_value=1.0, step=5.0, value=0, key=f"val_vale_{st.session_state['reset_ctr']}")
                data_vale = st.date_input("Data do Vale:", datetime.now(), key=f"dat_vale_{st.session_state['reset_ctr']}")
                motivo_vale = st.text_input("Observação/Motivo (Opcional):", value="Adiantamento de Coletas", key=f"mot_vale_{st.session_state['reset_ctr']}")
                
                if st.button("Lançar Vale", type="primary"):
                    try:
                        # Forçando a conversão exata dos tipos aceitos pelo Supabase
                        novo_vale = {
                            "data": str(data_vale),               # Garante texto da data AAAA-MM-DD
                            "coletor": str(coletor_vale).strip(), # Texto limpo do coletor
                            "valor_vale": float(valor_vale_input),# Força número decimal (numeric)
                            "descricao": str(motivo_vale).strip() # Texto da descrição
                        }
                        
                        supabase.table("vales_coleta").insert(novo_vale).execute()
                        st.success(f"✅ Vale de R$ {valor_vale_input:.2f} registrado para {coletor_vale}!")
                        
                        st.session_state["reset_ctr"] += 1
                        st.rerun()
                    except Exception as vale_err:
                        st.error(f"⚠️ Erro ao salvar o vale no banco: {vale_err}")
            else:
                st.info("Nenhum coletor cadastrado para receber vales.")

        # --- 3. CADASTRO DE USUÁRIOS ---
        with sub_menu_adm[2]:
            st.subheader("👤 Cadastrar Novo Usuário")
            novo_nome = st.text_input("Nome Completo:", key=f"nn_{st.session_state['reset_ctr']}")
            novo_usuario = st.text_input("Login de Acesso:", key=f"nu_{st.session_state['reset_ctr']}").strip().lower()
            nova_senha = st.text_input("Senha:", type="password", key=f"ns_{st.session_state['reset_ctr']}")
            novo_perfil = st.selectbox("Tipo de Perfil:", ["COLETOR", "ADM"], key=f"np_{st.session_state['reset_ctr']}")
            
            if st.button("Salvar Usuário", type="primary"):
                if novo_nome and novo_usuario and nova_senha:
                    res_check = supabase.table("usuarios").select("*").eq("usuario", novo_usuario).execute()
                    if res_check.data:
                        st.error("⚠️ Usuário já existe!")
                    else:
                        novo_user_dict = {
                            "usuario": novo_usuario, "senha": str(nova_senha),
                            "nome_completo": novo_nome, "cargo": novo_perfil
                        }
                        supabase.table("usuarios").insert(novo_user_dict).execute()
                        st.success(f"🎉 {novo_nome} cadastrado como {novo_perfil}!")
                        st.session_state["reset_ctr"] += 1
                        st.rerun()

    # =========================================================================
    # PERFIL COLETOR
    # =========================================================================
    else:
        menu = st.tabs(["📲 Enviar Coleta", "📊 Minhas Coletas", "💰 Meus Vales"])

        # 1. ENVIAR COLETA
        with menu[0]:
            st.header("Novo Envio")
            st.info(f"Registrando para: **{st.session_state['nome_completo_atual']}**")
            
            quantidade = st.number_input("Quantidade de aparelhos:", min_value=1, step=1, value=1, key=f"qtd_c_{st.session_state['reset_ctr']}")
            foto_comprovante = st.file_uploader("Selecione ou tire a foto do comprovante:", type=["png", "jpg", "jpeg"], key=f"foto_c_{st.session_state['reset_ctr']}")
                
            if st.button("Enviar para Aprovação", type="primary", use_container_width=True):
                if quantidade and foto_comprovante:
                    try:
                        with st.spinner("Enviando foto para o servidor..."):
                            nome_foto_nuvem = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{st.session_state['usuario_atual']}.png"
                            conteudo_foto = foto_comprovante.getvalue()
                            
                            # Upload no Storage (Sua RLS SQL já corrigiu isso!)
                            supabase.storage.from_("comprovantes").upload(
                                path=nome_foto_nuvem,
                                file=conteudo_foto,
                                file_options={"content-type": "image/png"}
                            )
                            
                            foto_url_final = supabase.storage.from_("comprovantes").get_public_url(nome_foto_nuvem)
                            
                            # 100% Alinhado com as colunas originais (data, coletor, quantidade, foto_url...)
                            novo_registro = {
                                "data": datetime.now().strftime("%Y-%m-%d"), 
                                "coletor": st.session_state['nome_completo_atual'], 
                                "quantidade": int(quantidade),
                                "foto_url": foto_url_final, 
                                "status": "Pendente", 
                                "valor_total": round(float(quantidade * VALOR_POR_COLETA), 2),
                                "pago": False
                            }
                            
                            supabase.table("coletas").insert(novo_registro).execute()
                            st.success("✅ Envio realizado com sucesso!")
                            
                            # Modifica o ID dos inputs para limpar a tela e reinicia
                            st.session_state["reset_ctr"] += 1
                            st.rerun()
                    except Exception as err:
                        st.error(f"⚠️ Erro no processo de envio: {err}")
                else:
                    st.error("⚠️ Por favor, adicione a foto do comprovante antes de enviar.")

        # 2. HISTÓRICO DE COLETAS (COLETOR)
        with menu[1]:
            st.header("Meu Histórico")
            
            st.markdown("#### 🔍 Filtrar Período")
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                c_data_ini = st.date_input("De:", value=st.session_state["c_filtro_inicio"], key="c_ini")
            with col_c2:
                c_data_fim = st.date_input("Até:", value=st.session_state["c_filtro_fim"], key="c_fim")
            
            st.session_state["c_filtro_inicio"] = c_data_ini
            st.session_state["c_filtro_fim"] = c_data_fim
            
            try:
                res_coletas_c = supabase.table("coletas").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                df = pd.DataFrame(res_coletas_c.data) if res_coletas_c.data else pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
            except Exception:
                df = pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
                
            if df.empty:
                st.info("Nenhuma coleta encontrada.")
            else:
                df['data_dt'] = pd.to_datetime(df['data'])
                dados_coletor = df[(df['data_dt'] >= pd.to_datetime(c_data_ini)) & (df['data_dt'] <= pd.to_datetime(c_data_fim))]
                
                if dados_coletor.empty:
                    st.info("Nenhuma coleta encontrada para este período.")
                else:
                    aprovadas = dados_coletor[dados_coletor["status"] == "Aprovado"]
                    
                    try:
                        res_vales_c = supabase.table("vales_coleta").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                        df_vales = pd.DataFrame(res_vales_c.data) if res_vales_c.data else pd.DataFrame(columns=["data", "valor_vale"])
                    except Exception:
                        df_vales = pd.DataFrame(columns=["data", "valor_vale"])
                        
                    if not df_vales.empty:
                        df_vales['data_dt'] = pd.to_datetime(df_vales['data'])
                        vales_dele = df_vales[(df_vales['data_dt'] >= pd.to_datetime(c_data_ini)) & (df_vales['data_dt'] <= pd.to_datetime(c_data_fim))]["valor_vale"].sum()
                    else:
                        vales_dele = 0.0
                    
                    total_ja_pago = aprovadas[aprovadas["pago"] == "Sim"]["valor_total"].sum() if not aprovadas.empty else 0.0
                    total_nao_pago = aprovadas[aprovadas["pago"] != "Sim"]["valor_total"].sum() if not aprovadas.empty else 0.0
                    
                    total_liquido_coletor = max(0.0, round(float(total_nao_pago) - float(vales_dele), 2))
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Líquido a Receber", f"R$ {total_liquido_coletor:.2f}")
                    c2.metric("Vales no Período (-)", f"R$ {vales_dele:.2f}")
                    c3.metric("Valor Já Pago", f"R$ {total_ja_pago:.2f}")
                    
                    st.markdown("### Envios do Período")
                    for idx, row in dados_coletor.iloc[::-1].iterrows():
                        status_cor = "🟢" if row['status'] == "Aprovado" else "🟡" if row['status'] == "Pendente" else "🔴"
                        status_pago_txt = "💰 Pago" if row.get('pago') == "Sim" else "⏳ Pendente de Pgto"
                        
                        if row['status'] == "Recusado":
                            with st.expander(f"🔴 Data: {row['data']} | Qtd: {row['quantidade']} | REPROVADA"):
                                st.write("❌ Esta solicitação foi recusada pela gerência.")
                        else:
                            with st.expander(f"{status_cor} Data: {row['data']} | Qtd: {row['quantidade']} | {status_pago_txt}"):
                                st.write(f"**Valor:** R$ {float(row['valor_total']):.2f}")
                                link_foto = row.get('foto_url')
                                if link_foto: st.image(link_foto, width=150)

        # 3. VISÃO DE VALES DO COLETOR
        with menu[2]:
            st.header("💸 Meus Adiantamentos (Vales)")
            try:
                res_vales_c2 = supabase.table("vales_coleta").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                df_v = pd.DataFrame(res_vales_c2.data) if res_vales_c2.data else pd.DataFrame(columns=["data", "valor_vale", "descricao"])
            except Exception:
                df_v = pd.DataFrame(columns=["data", "valor_vale", "descricao"])
                
            if df_v.empty:
                st.info("Nenhum vale registrado.")
            else:
                df_v['data_dt'] = pd.to_datetime(df_v['data'])
                vales_coletor = df_v[(df_v['data_dt'] >= pd.to_datetime(st.session_state["c_filtro_inicio"])) & (df_v['data_dt'] <= pd.to_datetime(st.session_state["c_filtro_fim"]))]
                
                if vales_coletor.empty:
                    st.info("Nenhum vale registrado para o período selecionado.")
                else:
                    st.metric("Total em Vales no Período", f"R$ {vales_coletor['valor_vale'].sum():.2f}")
                    if 'data_dt' in vales_coletor.columns:
                        vales_coletor = vales_coletor.drop(columns=['data_dt'])
                    st.dataframe(vales_coletor[["data", "valor_vale", "descricao"]], use_container_width=True)