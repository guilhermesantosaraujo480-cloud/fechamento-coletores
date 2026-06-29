import streamlit as st
import pandas as pd
from datetime import datetime
import time
import uuid
from supabase import create_client, Client
from io import BytesIO
from PIL import Image
import urllib.parse

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

# ----------------- OTIMIZAÇÃO: CACHE PARA LISTAGEM DE USUÁRIOS -----------------
@st.cache_data(ttl=600)
def listar_usuarios_cache():
    try:
        resposta = supabase.table("usuarios").select("*").execute()
        return resposta.data if resposta.data else []
    except Exception:
        return []

# ----------------- INICIALIZAÇÃO DO STATE -----------------
data_hoje = datetime.now().date()
primeiro_dia_mes = data_hoje.replace(day=1)

if "logado" not in st.session_state:
    st.session_state["logado"] = False
    st.session_state["usuario_atual"] = None
    st.session_state["nome_completo_atual"] = None
    st.session_state["cargo_atual"] = None

if "reset_ctr" not in st.session_state:
    st.session_state["reset_ctr"] = 0

if "input_data_ini" not in st.session_state:
    st.session_state["input_data_ini"] = primeiro_dia_mes
if "input_data_fim" not in st.session_state:
    st.session_state["input_data_fim"] = data_hoje
if "input_coletor_sel" not in st.session_state:
    st.session_state["input_coletor_sel"] = "Todos"

if "v_adm_filtro_inicio" not in st.session_state:
    st.session_state["v_adm_filtro_inicio"] = primeiro_dia_mes
if "v_adm_filtro_fim" not in st.session_state:
    st.session_state["v_adm_filtro_fim"] = data_hoje
if "v_adm_coletor_sel" not in st.session_state:
    st.session_state["v_adm_coletor_sel"] = "Todos"

if "c_filtro_inicio" not in st.session_state:
    st.session_state["c_filtro_inicio"] = primeiro_dia_mes
if "c_filtro_fim" not in st.session_state:
    st.session_state["c_filtro_fim"] = data_hoje

def limpar_filtros_callback():
    st.session_state["input_data_ini"] = primeiro_dia_mes
    st.session_state["input_data_fim"] = data_hoje
    st.session_state["input_coletor_sel"] = "Todos"

# ----------------- RECUPERAÇÃO DE SESSÃO VIA TOKEN -----------------
if not st.session_state["logado"] and "session" in st.query_params:
    token_url = st.query_params["session"]
    try:
        resposta = supabase.table("usuarios").select("*").eq("session_token", token_url).execute()
        if resposta.data:
            st.session_state["logado"] = True
            st.session_state["usuario_atual"] = resposta.data[0]["usuario"]
            st.session_state["nome_completo_atual"] = resposta.data[0]["nome_completo"]
            st.session_state["cargo_atual"] = resposta.data[0]["cargo"]
    except Exception:
        pass 

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
                novo_token = str(uuid.uuid4())
                id_usuario = user_valido[0]["id"]
                supabase.table("usuarios").update({"session_token": novo_token}).eq("id", id_usuario).execute()
                
                st.session_state["logado"] = True
                st.session_state["usuario_atual"] = user_input
                st.session_state["nome_completo_atual"] = user_valido[0]["nome_completo"]
                st.session_state["cargo_atual"] = user_valido[0]["cargo"]
                st.query_params["session"] = novo_token
                
                st.success(f"Bem-vindo, {st.session_state['nome_completo_atual']}!")
                time.sleep(0.1)
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
        except Exception as e:
            st.error(f"Erro ao conectar com o banco de dados: {e}")

# ----------------- ÁREA DO SISTEMA (LOGADO) -----------------
else:
    col_user, col_logout = st.columns([3, 1])
    col_user.write(f"👤 Conectado: **{st.session_state['nome_completo_atual']}** ({st.session_state['cargo_atual']})")
    
    if col_logout.button("Sair", use_container_width=True):
        try:
            supabase.table("usuarios").update({"session_token": None}).eq("usuario", st.session_state["usuario_atual"]).execute()
        except Exception:
            pass
            
        st.query_params.clear()
        st.session_state["logado"] = False
        st.session_state["usuario_atual"] = None
        st.session_state["nome_completo_atual"] = None
        st.session_state["cargo_atual"] = None
        st.rerun()

    # =========================================================================
    # PERFIL ADMINISTRADOR
    # =========================================================================
    if st.session_state["cargo_atual"] == "ADM":
        st.subheader("🛡️ Painel do Administrador")
        
        try:
            res_coletas = supabase.table("coletas").select("*").execute()
            res_vales = supabase.table("vales_coleta").select("*").execute()
            res_premiacoes = supabase.table("premiacoes").select("*").execute()
            res_users_data = listar_usuarios_cache()
            
            df_bruto_coletas = pd.DataFrame(res_coletas.data) if res_coletas.data else pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
            df_bruto_vales = pd.DataFrame(res_vales.data) if res_vales.data else pd.DataFrame(columns=["id", "data", "coletor", "valor_vale", "descricao", "foto_url"])
            df_bruto_premiacoes = pd.DataFrame(res_premiacoes.data) if res_premiacoes.data else pd.DataFrame(columns=["id", "data", "coletor", "valor_premiacao", "descricao"])
            lista_coletores = ["Todos"] + [u["nome_completo"] for u in res_users_data if u.get("cargo") == "COLETOR"]
        except Exception as e:
            st.error(f"Erro ao carregar dados do banco: {e}")
            df_bruto_coletas = pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
            df_bruto_vales = pd.DataFrame(columns=["id", "data", "coletor", "valor_vale", "descricao", "foto_url"])
            df_bruto_premiacoes = pd.DataFrame(columns=["id", "data", "coletor", "valor_premiacao", "descricao"])
            lista_coletores = ["Todos"]

        sub_menu_adm = st.tabs(["📋 Gestão de Coletas", "📉 Registrar/Ver Vales", "🏅 Serviços/Premiações", "👤 Cadastrar Usuários"])
        
        # ----------------- ABA 1: GESTÃO DE COLETAS -----------------
        with sub_menu_adm[0]:
            st.markdown("### 🔍 Filtros Gerais do Período")
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                data_inicio = st.date_input("Data Início:", key="input_data_ini")
            with col_f2:
                data_fim = st.date_input("Data Fim:", key="input_data_fim")
            with col_f3:
                idx_default = lista_coletores.index(st.session_state["input_coletor_sel"]) if st.session_state["input_coletor_sel"] in lista_coletores else 0
                coletor_sel = st.selectbox("Filtrar por Coletor:", lista_coletores, index=idx_default, key="input_coletor_sel")

            st.button("❌ Limpar Filtros de Coletas", on_click=limpar_filtros_callback, use_container_width=True)
            st.markdown("---")

            if not df_bruto_coletas.empty:
                df_bruto_coletas['data_dt'] = pd.to_datetime(df_bruto_coletas['data']).dt.date
                df_filtrado = df_bruto_coletas[(df_bruto_coletas['data_dt'] >= data_inicio) & (df_bruto_coletas['data_dt'] <= data_fim)].copy()
                if coletor_sel != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["coletor"] == coletor_sel]
            else:
                df_filtrado = df_bruto_coletas.copy()

            if not df_bruto_vales.empty:
                df_bruto_vales['data_dt'] = pd.to_datetime(df_bruto_vales['data']).dt.date
                vales_financeiro = df_bruto_vales[(df_bruto_vales['data_dt'] >= data_inicio) & (df_bruto_vales['data_dt'] <= data_fim)].copy()
                if coletor_sel != "Todos":
                    vales_financeiro = vales_financeiro[vales_financeiro["coletor"] == coletor_sel]
            else:
                vales_financeiro = df_bruto_vales.copy()

            if not df_bruto_premiacoes.empty:
                df_bruto_premiacoes['data_dt'] = pd.to_datetime(df_bruto_premiacoes['data']).dt.date
                premiacoes_financeiro = df_bruto_premiacoes[(df_bruto_premiacoes['data_dt'] >= data_inicio) & (df_bruto_premiacoes['data_dt'] <= data_fim)].copy()
                if coletor_sel != "Todos":
                    premiacoes_financeiro = premiacoes_financeiro[premiacoes_financeiro["coletor"] == coletor_sel]
            else:
                premiacoes_financeiro = df_bruto_premiacoes.copy()

            aprovados_periodo = df_filtrado[df_filtrado["status"] == "Aprovado"] if not df_filtrado.empty else pd.DataFrame()
            nao_pagas_lista = aprovados_periodo[aprovados_periodo["pago"] != True] if not aprovados_periodo.empty else pd.DataFrame()
            ja_pagas_lista = aprovados_periodo[aprovados_periodo["pago"] == True] if not aprovados_periodo.empty else pd.DataFrame()

            container_botoes_massa = st.container()
            with container_botoes_massa:
                if coletor_sel != "Todos" and not nao_pagas_lista.empty:
                    confirma_pagamento = st.checkbox(f"🔒 Desbloquear botão de pagamento em massa para {coletor_sel}", key="chk_confirma")
                    if confirma_pagamento:
                        if st.button(f"💰 Marcar TODAS as Coletas de {coletor_sel} como Pagas", type="primary", use_container_width=True):
                            with st.spinner("Processando..."):
                                ids_para_pagar = nao_pagas_lista["id"].tolist()
                                for cid in ids_para_pagar:
                                    supabase.table("coletas").update({"pago": True}).eq("id", cid).execute()
                            st.success(f"✅ Sucesso! {len(ids_para_pagar)} coletas foram pagas.")
                            time.sleep(0.4)
                            st.rerun()
                    else:
                        st.button(f"💰 Marcar TODAS as Coletas de {coletor_sel} como Pagas (Marque a caixa)", disabled=True, use_container_width=True)

            st.subheader("📥 Coletas Pendentes no Período")
            pendentes = df_filtrado[df_filtrado["status"] == "Pendente"] if not df_filtrado.empty else pd.DataFrame()
            
            if pendentes.empty:
                st.info("Nenhuma coleta pendente encontrada.")
            else:
                for index, row in pendentes.iterrows():
                    col1, col2 = st.columns([3, 2])
                    with col1:
                        st.write(f"**Coletor:** {row['coletor']} | **Qtd:** {row['quantidade']} un | **Data:** {row['data']}")
                        link_foto = row.get('foto_url')
                        if link_foto: st.image(link_foto, width=150)
                    with col2:
                        if st.button("✓ Aprovar", key=f"ap_{row['id']}", type="primary"):
                            supabase.table("coletas").update({"status": "Aprovado"}).eq("id", row["id"]).execute()
                            st.rerun()
                        if st.button("✕ Recusar", key=f"rec_{row['id']}"):
                            supabase.table("coletas").update({"status": "Recusado"}).eq("id", row["id"]).execute()
                            st.rerun()
                    st.markdown("---")
            
            st.subheader("💵 Fechamento Financeiro")
            total_vales = vales_financeiro["valor_vale"].sum() if not vales_financeiro.empty else 0.0
            total_premiacoes = premiacoes_financeiro["valor_premiacao"].sum() if not premiacoes_financeiro.empty else 0.0
            total_bruto = (aprovados_periodo["valor_total"].sum() if not aprovados_periodo.empty else 0.0) + float(total_premiacoes)
            total_ja_pago = ja_pagas_lista["valor_total"].sum() if not ja_pagas_lista.empty else 0.0
            total_nao_pago_adm = (nao_pagas_lista["valor_total"].sum() if not nao_pagas_lista.empty else 0.0) + float(total_premiacoes)
            total_liquido = float(total_nao_pago_adm) - float(total_vales)
            
            cm1, cm2, cm3 = st.columns(3)
            cm1.metric("Bruto Período", f"R$ {total_bruto:.2f}")
            cm2.metric("Valor Já Pago", f"R$ {total_ja_pago:.2f}")
            cm3.metric("Desconto Vales (-)", f"R$ {total_vales:.2f}")
            
            if total_liquido < 0:
                st.markdown(f"<p style='font-size:14px; margin-bottom:0px; color:#888;'>Líquido a Pagar</p><h2 style='color:#FF4B4B; margin-top:0px; font-weight:normal;'>-R$ {abs(total_liquido):.2f}</h2>", unsafe_allow_html=True)
            else:
                st.metric("Líquido a Pagar", f"R$ {total_liquido:.2f}")
            
            container_recibo = st.container()
            with container_recibo:
                if coletor_sel != "Todos":
                    texto_recibo = (
                        f"*FECHAMENTO DE COLETAS*\n"
                        f"*Coletor:* {coletor_sel}\n"
                        f"*Período:* {data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}\n"
                        f"-----------------------------\n"
                        f"💰 *Total Bruto Aprovado (com prêmios):* R$ {total_bruto:.2f}\n"
                        f"💵 *Valor Já Pago:* R$ {total_ja_pago:.2f}\n"
                        f"📉 *Desconto em Vales:* R$ {total_vales:.2f}\n"
                        f"💵 *Líquido à Pagar Restante:* {'-' if total_liquido < 0 else ''}R$ {abs(total_liquido):.2f}\n"
                        f"-----------------------------\n"
                        f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}"
                    )
                    st.text_area("📋 Texto do Recibo", value=texto_recibo, height=180, key=f"rec_{coletor_sel}")
            
            st.markdown("#### Detalhes dos Aprovados")
            if aprovados_periodo.empty:
                st.info("Nenhuma coleta aprovada neste período.")
            else:
                for index, row in aprovados_periodo.iterrows():
                    pago_atual = row.get('pago', False)
                    status_pago_txt = "✅ Já Pago" if pago_atual else "❌ Não Pago"
                    col_p1, col_p2 = st.columns([3, 2])
                    with col_p1:
                        st.write(f"**{row['coletor']}** | R$ {float(row['valor_total']):.2f} | Data: {row['data']} ({status_pago_txt})")
                    with col_p2:
                        if not pago_atual:
                            if st.button("Marcar como Pago", key=f"pag_{row['id']}"):
                                supabase.table("coletas").update({"pago": True}).eq("id", row["id"]).execute()
                                st.rerun()
                    st.markdown("---")

        # ----------------- ABA 2: REGISTRAR/VER VALES -----------------
        with sub_menu_adm[1]:
            st.subheader("💰 Registrar Vale / Adiantamento")
            coletores_vales = [u["nome_completo"] for u in res_users_data if u.get("cargo") == "COLETOR"]
            
            if coletores_vales:
                coletor_vale = st.selectbox("Selecione o Coletor para o Vale:", coletores_vales, key=f"sv_{st.session_state['reset_ctr']}")
                valor_vale_input = st.number_input("Valor (R$):", min_value=1.0, value=10.0, key=f"vv_{st.session_state['reset_ctr']}")
                data_vale = st.date_input("Data do Vale:", datetime.now(), key=f"dv_{st.session_state['reset_ctr']}")
                foto_vale = st.file_uploader("Foto do comprovante:", type=["png", "jpg", "jpeg"], key=f"fv_{st.session_state['reset_ctr']}")
                motivo_vale = st.text_input("Observação:", value="Adiantamento de Coletas", key=f"mv_{st.session_state['reset_ctr']}")
                
                if st.button("Lançar Vale"):
                    if foto_vale:
                        try:
                            img = Image.open(foto_vale)
                            img.thumbnail((1024, 1024))
                            buffer_memoria = BytesIO()
                            img.save(buffer_memoria, format="JPEG", quality=75)
                            
                            nome_foto_nuvem = f"vale_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                            supabase.storage.from_("comprovantes").upload(path=nome_foto_nuvem, file=buffer_memoria.getvalue(), file_options={"content-type": "image/jpeg"})
                            foto_url_final = supabase.storage.from_("comprovantes").get_public_url(nome_foto_nuvem)
                            
                            supabase.table("vales_coleta").insert({"data": str(data_vale), "coletor": coletor_vale, "valor_vale": valor_vale_input, "descricao": motivo_vale, "foto_url": foto_url_final}).execute()
                            st.success("✅ Vale registrado!")
                            st.session_state["reset_ctr"] += 1
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro: {e}")
            
            st.markdown("---")
            st.subheader("📋 Histórico de Vales Emitidos")
            col_v1, col_v2, col_v3 = st.columns(3)
            with col_v1: v_data_ini = st.date_input("De (Vale):", key="v_ini_adm")
            with col_v2: v_data_fim = st.date_input("Até (Vale):", key="v_fim_adm")
            with col_v3: coletor_sel_v = st.selectbox("Coletor (Vale):", lista_coletores, key=f"v_col_adm")
            
            if not df_bruto_vales.empty:
                df_bruto_vales['data_dt'] = pd.to_datetime(df_bruto_vales['data']).dt.date
                vales_filtrados_historico = df_bruto_vales[(df_bruto_vales['data_dt'] >= v_data_ini) & (df_bruto_vales['data_dt'] <= v_data_fim)].copy()
                if coletor_sel_v != "Todos":
                    vales_filtrados_historico = vales_filtrados_historico[vales_filtrados_historico["coletor"] == coletor_sel_v]
                
                for idx_v, row_v in vales_filtrados_historico.sort_values(by="data", ascending=False).iterrows():
                    st.write(f"📅 {row_v['data']} | **{row_v['coletor']}** | R$ {row_v['valor_vale']:.2f}")
                    if row_v.get('foto_url'): st.image(row_v['foto_url'], width=120)
                    st.markdown("---")

        # ----------------- ABA 3: SERVIÇOS/PREMIAÇÕES -----------------
        with sub_menu_adm[2]:
            st.subheader("🏅 Registrar Serviço Extra / Premiação")
            coletores_premios = [u["nome_completo"] for u in res_users_data if u.get("cargo") == "COLETOR"]
            if coletores_premios:
                coletor_premio = st.selectbox("Coletor:", coletores_premios, key=f"sp_{st.session_state['reset_ctr']}")
                valor_premio_input = st.number_input("Valor (R$):", min_value=1.0, value=50.0, key=f"vp_{st.session_state['reset_ctr']}")
                data_premio = st.date_input("Data:", datetime.now(), key=f"dp_{st.session_state['reset_ctr']}")
                motivo_premio = st.text_input("Descrição:", value="Meta Atingida", key=f"mp_{st.session_state['reset_ctr']}")
                
                if st.button("Lançar Premiação"):
                    supabase.table("premiacoes").insert({"data": str(data_premio), "coletor": coletor_premio, "valor_premiacao": valor_premio_input, "descricao": motivo_premio}).execute()
                    st.success("✅ Lançado!")
                    st.session_state["reset_ctr"] += 1
                    st.rerun()

        # ----------------- ABA 4: CADASTRO DE USUÁRIOS -----------------
        with sub_menu_adm[3]:
            st.subheader("👤 Cadastrar Novo Usuário")
            novo_nome = st.text_input("Nome Completo:", key=f"nn_{st.session_state['reset_ctr']}")
            novo_usuario = st.text_input("Login:", key=f"nu_{st.session_state['reset_ctr']}").strip().lower()
            nova_senha = st.text_input("Senha:", type="password", key=f"ns_{st.session_state['reset_ctr']}")
            novo_perfil = st.selectbox("Perfil:", ["COLETOR", "ADM"], key=f"np_{st.session_state['reset_ctr']}")
            
            if st.button("Salvar Usuário"):
                if novo_nome and novo_usuario and nova_senha:
                    supabase.table("usuarios").insert({"usuario": novo_usuario, "senha": str(nova_senha), "nome_completo": novo_nome, "cargo": novo_perfil}).execute()
                    st.cache_data.clear()
                    st.success("🎉 Cadastrado!")
                    st.session_state["reset_ctr"] += 1
                    st.rerun()

    # =========================================================================
    # PERFIL COLETOR
    # =========================================================================
    else:
        menu = st.tabs(["📲 Enviar Coleta", "📊 Minhas Coletas", "💰 Meus Vales", "📄 Comprovantes"])

        with menu[0]:
            st.header("Novo Envio")
            quantidade = st.number_input("Quantidade:", min_value=1, step=1, value=1, key=f"qc_{st.session_state['reset_ctr']}")
            foto_comprovante = st.file_uploader("Foto do comprovante:", type=["png", "jpg", "jpeg"], key=f"fc_{st.session_state['reset_ctr']}")
                
            if st.button("Enviar para Aprovação", type="primary", use_container_width=True):
                if quantidade and foto_comprovante:
                    try:
                        img = Image.open(foto_comprovante)
                        img.thumbnail((1024, 1024))
                        buffer_memoria = BytesIO()
                        img.save(buffer_memoria, format="JPEG", quality=75)
                        
                        nome_foto_nuvem = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{st.session_state['usuario_atual']}.jpg"
                        supabase.storage.from_("comprovantes").upload(path=nome_foto_nuvem, file=buffer_memoria.getvalue(), file_options={"content-type": "image/jpeg"})
                        foto_url_final = supabase.storage.from_("comprovantes").get_public_url(nome_foto_nuvem)
                        
                        supabase.table("coletas").insert({
                            "data": datetime.now().strftime("%Y-%m-%d"), 
                            "coletor": st.session_state['nome_completo_atual'], 
                            "quantidade": int(quantidade),
                            "foto_url": foto_url_final, 
                            "status": "Pendente", 
                            "valor_total": round(float(quantidade * VALOR_POR_COLETA), 2),
                            "pago": False
                        }).execute()
                        st.success("✅ Enviado!")
                        st.session_state["reset_ctr"] += 1
                        st.rerun()
                    except Exception as err:
                        st.error(f"Erro: {err}")

        with menu[1]:
            st.header("Meu Histórico")
            col_c1, col_c2 = st.columns(2)
            with col_c1: c_data_ini = st.date_input("De:", key="c_ini_p")
            with col_c2: c_data_fim = st.date_input("Até:", key="c_fim_p")
            
            try:
                res_coletas_c = supabase.table("coletas").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                df = pd.DataFrame(res_coletas_c.data) if res_coletas_c.data else pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
            except Exception:
                df = pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
                
            if not df.empty:
                df['data_dt'] = pd.to_datetime(df['data']).dt.date
                dados_coletor = df[(df['data_dt'] >= c_data_ini) & (df['data_dt'] <= c_data_fim)]
                
                aprovadas = dados_coletor[dados_coletor["status"] == "Aprovado"] if not dados_coletor.empty else pd.DataFrame()
                
                try:
                    res_vales_c = supabase.table("vales_coleta").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                    df_vales = pd.DataFrame(res_vales_c.data) if res_vales_c.data else pd.DataFrame(columns=["data", "valor_vale"])
                except Exception:
                    df_vales = pd.DataFrame(columns=["data", "valor_vale"])
                    
                try:
                    res_premiacoes_c = supabase.table("premiacoes").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                    df_premiacoes_c = pd.DataFrame(res_premiacoes_c.data) if res_premiacoes_c.data else pd.DataFrame(columns=["data", "valor_premiacao", "descricao"])
                except Exception:
                    df_premiacoes_c = pd.DataFrame(columns=["data", "valor_premiacao", "descricao"])

                vales_dele = df_vales[(pd.to_datetime(df_vales['data']).dt.date >= c_data_ini) & (pd.to_datetime(df_vales['data']).dt.date <= c_data_fim)]["valor_vale"].sum() if not df_vales.empty else 0.0
                premiacoes_dele = df_premiacoes_c[(pd.to_datetime(df_premiacoes_c['data']).dt.date >= c_data_ini) & (pd.to_datetime(df_premiacoes_c['data']).dt.date <= c_data_fim)]["valor_premiacao"].sum() if not df_premiacoes_c.empty else 0.0
                
                total_ja_pago_c = aprovadas[aprovadas["pago"] == True]["valor_total"].sum() if not aprovadas.empty else 0.0
                total_nao_pago_c = (aprovadas[aprovadas["pago"] != True]["valor_total"].sum() if not aprovadas.empty else 0.0) + float(premiacoes_dele)
                total_liquido_coletor = round(float(total_nao_pago_c) - float(vales_dele), 2)
                
                st.metric("Líquido a Receber", f"R$ {total_liquido_coletor:.2f}")
                
                for idx, row in dados_coletor.iloc[::-1].iterrows():
                    with st.expander(f"Data: {row['data']} | Status: {row['status']}"):
                        st.write(f"Quantidade: {row['quantidade']} | Valor: R$ {row['valor_total']:.2f}")
                        if row.get('foto_url'): st.image(row['foto_url'], width=120)

        with menu[2]:
            st.header("🔑 Meus Adiantamentos (Vales)")
            try:
                res_vales_c2 = supabase.table("vales_coleta").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                df_v = pd.DataFrame(res_vales_c2.data) if res_vales_c2.data else pd.DataFrame(columns=["data", "valor_vale", "descricao", "foto_url"])
            except Exception:
                df_v = pd.DataFrame(columns=["data", "valor_vale", "descricao", "foto_url"])
                
            if not df_v.empty:
                df_v['data_dt'] = pd.to_datetime(df_v['data']).dt.date
                vales_coletor = df_v[(df_v['data_dt'] >= c_data_ini) & (df_v['data_dt'] <= c_data_fim)]
                for idx_vc, row_vc in vales_coletor.sort_values(by="data", ascending=False).iterrows():
                    with st.expander(f"Vale R$ {row_vc['valor_vale']:.2f} ({row_vc['data']})"):
                        st.write(f"Descrição: {row_vc['descricao']}")
                        if row_vc.get('foto_url'): st.image(row_vc['foto_url'], width=120)

        with menu[3]:
            st.subheader("🔍 Localizar Comprovante")
            termo_busca = st.text_input("Digite a OS ou Cliente:").strip()
            if termo_busca:
                try:
                    resposta = supabase.table("comprovantes_clientes").select("*").or_(f"cliente.ilike.%{termo_busca}%,ordem_servico.ilike.%{termo_busca}%").execute()
                    if resposta.data:
                        for registro in resposta.data:
                            st.write(f"OS: {registro['ordem_servico']} | {registro['cliente']}")
                            st.link_button("Abrir PDF", registro['arquivo_url'])
                except Exception as e:
                    st.error(f"Erro na busca: {e}")