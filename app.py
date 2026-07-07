import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import time
import uuid  # Gerador de tokens ultra-seguros
from supabase import create_client, Client
from io import BytesIO
from PIL import Image  # Para Compactação de fotos
import urllib.parse
from streamlit_cookies_controller import CookieController  # Controlador de Cookies

# Configuração da página (otimizada para celular)
st.set_page_config(page_title="Sistema Vivo Coletas", layout="centered", initial_sidebar_state="collapsed")

# VALOR PADRÃO POR COLETA
VALOR_POR_COLETA = 10.0

# Inicializa o controlador de cookies de forma segura
cookies = CookieController()

# --- FUNÇÃO DE AJUSTE DE HORÁRIO OFICIAL DE BRASÍLIA (UTC-3) ---
def obter_agora_brasilia():
    """Retorna o datetime atual ajustado manualmente para o fuso de Brasília (UTC-3)"""
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(fuso_brasilia)

# ----------------- CONEXÃO COM O BANCO DE DADOS (SUPABASE) -----------------\
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- FUNÇÃO AUXILIAR ULTRA-SEGURA PARA VALIDAR E EXTRAIR URL DO SUPABASE ---
def extrair_url_valida(foto_obj):
    """Garante que obteremos uma URL válida de internet e evita que o st.image quebre"""
    if not foto_obj:
        return None
    if isinstance(foto_obj, dict):
        url = foto_obj.get("publicUrl") or foto_obj.get("public_url")
    else:
        url = str(foto_obj).strip()
    if not url or url.lower() in ["none", "null", "undefined", ""]:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return None

# ----------------- OTIMIZAÇÃO: CACHE PARA LISTAGEM DE USUÁRIOS -----------------\
@st.cache_data(ttl=600)
def listar_usuarios_cache():
    try:
        resposta = supabase.table("usuarios").select("*").execute()
        return resposta.data if resposta.data else []
    except Exception:
        return []

# ----------------- INICIALIZAÇÃO PREVENTIVA DE TODO O STATE -----------------\
agora_br = obtener_agora_brasilia()
data_hoje = agora_br.date()
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

if "c_filtro_inicio" not in st.session_state:
    st.session_state["c_filtro_inicio"] = primeiro_dia_mes
if "c_filtro_fim" not in st.session_state:
    st.session_state["c_filtro_fim"] = data_hoje

def limpar_filtros_callback():
    st.session_state["input_data_ini"] = primeiro_dia_mes
    st.session_state["input_data_fim"] = data_hoje
    st.session_state["input_coletor_sel"] = "Todos"

# ----------------- RECUPERAÇÃO DE SESSÃO AUTOMÁTICA (COOKIES / URL) -----------------\
token_recuperado = None

cookie_token = cookies.get("vivo_coletas_session")
if cookie_token:
    token_recuperado = cookie_token
elif "session" in st.query_params:
    token_recuperado = st.query_params["session"]

if not st.session_state["logado"] and token_recuperado:
    try:
        resposta = supabase.table("usuarios").select("*").eq("session_token", token_recuperado).execute()
        if resposta.data:
            st.session_state["logado"] = True
            st.session_state["usuario_atual"] = resposta.data[0]["usuario"]
            st.session_state["nome_completo_atual"] = resposta.data[0]["nome_completo"]
            st.session_state["cargo_atual"] = resposta.data[0]["cargo"]
            st.query_params["session"] = token_recuperado
    except Exception:
        pass 

st.title("📱 Sistema de Coletas")
st.markdown("---")

# ----------------- TELA DE LOGIN -----------------\
if not st.session_state["logado"]:
    st.subheader("🔑 Acesso ao Sistema")
    user_input = st.text_input("Usuário (Login):").strip().lower()
    pass_input = st.text_input("Senha:", type="password")
    
    lembrar_mim = st.checkbox("Manter-me conectado neste aparelho", value=True)
    
    if st.button("Entrar", type="primary", use_container_width=True):
        try:
            resposta = supabase.table("usuarios").select("*").eq("usuario", user_input).eq("senha", str(pass_input)).execute()
            user_valido = resposta.data
            
            if user_valido:
                novo_token = str(uuid.uuid4())
                id_usuario = user_valido[0]["id"]
                supabase.table("usuarios").update({"session_token": novo_token}).eq("id", id_usuario).execute()
                
                if lembrar_mim:
                    cookies.set("vivo_coletas_session", novo_token, max_age=2592000)
                
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

# ----------------- ÁREA DO SISTEMA (LOGADO) -----------------\
else:
    col_user, col_logout = st.columns([3, 1])
    col_user.write(f"👤 Conectado: **{st.session_state['nome_completo_atual']}** ({st.session_state['cargo_atual']})")
    
    if col_logout.button("Sair", use_container_width=True):
        try:
            supabase.table("usuarios").update({"session_token": None}).eq("usuario", st.session_state["usuario_atual"]).execute()
            cookies.remove("vivo_coletas_session")
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
        st.subheader("🛡️ Painel do Administrator")
        
        try:
            res_coletas = supabase.table("coletas").select("*").execute()
            res_vales = supabase.table("vales_coleta").select("*").execute()
            res_premiacoes = supabase.table("premiacoes").select("*").execute()
            res_users_data = listar_usuarios_cache()
            
            df_bruto_coletas = pd.DataFrame(res_coletas.data) if res_coletas.data else pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
            df_bruto_vales = pd.DataFrame(res_vales.data) if res_vales.data else pd.DataFrame(columns=["id", "data", "coletor", "valor_vale", "descricao", "foto_url"])
            df_bruto_premiacoes = pd.DataFrame(res_premiacoes.data) if res_premiacoes.data else pd.DataFrame(columns=["id", "data", "coletor", "valor_premiacao", "descricao"])
            
            if "pago" not in df_bruto_coletas.columns:
                df_bruto_coletas["pago"] = False
            else:
                df_bruto_coletas["pago"] = df_bruto_coletas["pago"].fillna(False)

            lista_coletores = ["Todos"] + [u["nome_completo"] for u in res_users_data if u.get("cargo") == "COLETOR"]
        except Exception as e:
            st.error(f"Erro ao carregar dados do banco: {e}")
            df_bruto_coletas = pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
            df_bruto_vales = pd.DataFrame(columns=["id", "data", "coletor", "valor_vale", "descricao", "foto_url"])
            df_bruto_premiacoes = pd.DataFrame(columns=["id", "data", "coletor", "valor_premiacao", "descricao"])
            lista_coletores = ["Todos"]

        # CORREÇÃO PARTE 1: Filtros isolados dentro de um container próprio para não arrastar o CSS das abas
        with st.container():
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

        # CORREÇÃO PARTE 2: Abas encapsuladas e usando KEY dinâmica baseada no coletor selecionado.
        # Isso força o navegador a desenhar as abas perfeitamente na horizontal sempre que o filtro mudar.
        with st.container():
            nome_limpo_chave = str(coletor_sel).replace(" ", "_")
            sub_menu_adm = st.tabs(
                ["📋 Gestão de Coletas", "📉 Registrar/Ver Vales", "🏅 Serviços/Premiações", "📊 Relatório de Uso", "👤 Cadastrar Usuários"], 
                key=f"tabs_adm_fix_{nome_limpo_chave}"
            )
        
        # ----------------- ABA 1: GESTÃO DE COLETAS -----------------
        with sub_menu_adm[0]:
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

            container_botoes_massa = st.container()
            with container_botoes_massa:
                if coletor_sel != "Todos" and not nao_pagas_lista.empty:
                    confirma_pagamento = st.checkbox(f"🔒 Desbloquear botão de controle de pagamento para {coletor_sel}", key="chk_confirma")
                    if confirma_pagamento:
                        if st.button(f"💰 Marcar TODAS as Coletas de {coletor_sel} como Pagas (Controle)", type="primary", use_container_width=True):
                            with st.spinner(f"Marcando como pago..."):
                                ids_para_pagar = nao_pagas_lista["id"].tolist()
                                for cid in ids_para_pagar:
                                    supabase.table("coletas").update({"pago": True}).eq("id", cid).execute()
                            st.success(f"✅ Sucesso! {len(ids_para_pagar)} coletas foram marcadas como pagas para seu controle.")
                            time.sleep(0.4)
                            st.rerun()
                    else:
                        st.button(f"💰 Marcar TODAS as Coletas de {coletor_sel} como Pagas (Marque a caixa acima)", type="secondary", disabled=True, use_container_width=True)

            st.subheader("📋 Coletas Pendentes de Aprovação")
            pendentes = df_filtrado[df_filtrado["status"] == "Pendente"] if not df_filtrado.empty else pd.DataFrame()
            
            if pendentes.empty:
                st.info("Nenhuma coleta pendente encontrada.")
            else:
                for index, row in pendentes.iterrows():
                    col1, col2 = st.columns([3, 2])
                    with col1:
                        st.write(f"**Coletor:** {row['coletor']} | **Qtd:** {row['quantidade']} un | **Data:** {row['data']}")
                        link_foto = extrair_url_valida(row.get('foto_url'))
                        if link_foto: 
                            st.image(link_foto, width=150)
                        else:
                            st.caption("📷 Sem foto anexada")
                    with col2:
                        if st.button(f"✓ Aprovar", key=f"ap_{row['id']}", type="primary"):
                            with st.spinner("Aprovando..."):
                                supabase.table("coletas").update({"status": "Aprovado"}).eq("id", row["id"]).execute()
                            st.rerun()
                        if st.button(f"✕ Recusar", key=f"rec_{row['id']}"):
                            with st.spinner("Recusando..."):
                                supabase.table("coletas").update({"status": "Recusado"}).eq("id", row["id"]).execute()
                            st.rerun()
                    st.markdown("---")
            
            st.subheader("💵 Fechamento Financeiro")
            total_vales = float(vales_financeiro["valor_vale"].sum()) if not vales_financeiro.empty else 0.0
            total_coletas_bruto = float(aprovados_periodo["valor_total"].sum()) if not aprovados_periodo.empty else 0.0
            total_premiacoes = float(premiacoes_financeiro["valor_premiacao"].sum()) if not premiacoes_financeiro.empty else 0.0
            total_liquido = (total_coletas_bruto + total_premiacoes) - total_vales
            
            cm1, cm2, cm3, cm4 = st.columns(4)
            cm1.metric("Bruto Aparelhos", f"R$ {total_coletas_bruto:.2f}")
            cm2.metric("Premiações (+)", f"R$ {total_premiacoes:.2f}")
            cm3.metric("Vales (-)", f"R$ {total_vales:.2f}")
            cm4.metric("Líquido a Pagar", f"R$ {total_liquido:.2f}")
            
            if total_liquido < 0:
                st.error(f"🔴 **Aviso:** Os vales superaram a produção deste coletor em **R$ {abs(total_liquido):.2f}**.")
            elif total_liquido == 0:
                st.success("🟢 **Conta Zerada:** Sem valores pendentes de repasse neste período.")
            else:
                st.info(f"🔵 **Líquido Final:** Realize o acerto de **R$ {total_liquido:.2f}** com o coletor.")

            container_recibo = st.container()
            with container_recibo:
                if coletor_sel != "Todos":
                    total_aparelhos = int(aprovados_periodo["quantidade"].sum()) if not aprovados_periodo.empty else 0
                    
                    texto_recibo = (
                        f"*FECHAMENTO DE COLETAS*\n"
                        f"*Coletor:* {coletor_sel}\n"
                        f"*Período:* {data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}\n"
                        f"-----------------------------\n"
                        f"📱 *Total de Aparelhos:* {total_aparelhos} un\n"
                        f"💰 *Total Bruto:* R$ {total_coletas_bruto:.2f}\n"
                        f"🎁 *Premiações/Extras:* R$ {total_premiacoes:.2f}\n"
                        f"📉 *Desconto em Vales:* R$ {total_vales:.2f}\n"
                        f"-----------------------------\n"
                        f"🧮 *Valor Líquido a Pagar:* R$ {total_liquido:.2f}\n"
                        f"-----------------------------\n"
                        f"Gerado em: {obter_agora_brasilia().strftime('%d/%m/%Y às %H:%M')}"
                    )
                    st.markdown("#### 📋 Texto do Recibo (Pronto para copiar)")
                    st.code(texto_recibo, language="text")
            
            st.markdown("#### Histórico e Controle Visual de Ganhos")
            
            lista_ganhos_adm = []
            if not aprovados_periodo.empty:
                for idx, row in aprovados_periodo.iterrows():
                    lista_ganhos_adm.append({
                        "id": row["id"], "tipo": "COLETA", "data": row["data"], "coletor": row["coletor"],
                        "valor": float(row["valor_total"]), "pago": row.get("pago", False), "detalhe": f"Qtd: {row['quantidade']} un"
                    })
            if not premiacoes_financeiro.empty:
                for idx, row in premiacoes_financeiro.iterrows():
                    lista_ganhos_adm.append({
                        "id": row["id"], "tipo": "PREMIACAO", "data": row["data"], "coletor": row["coletor"],
                        "valor": float(row["valor_premiacao"]), "pago": False, "detalhe": f"🏅 {row['descricao']}"
                    })
                    
            if not lista_ganhos_adm:
                st.info("Nenhum ganho aprovado ou premiação encontrada neste período.")
            else:
                for item in sorted(lista_ganhos_adm, key=lambda x: x["data"], reverse=True):
                    col_p1, col_p2 = st.columns([3, 2])
                    with col_p1:
                        if item["tipo"] == "COLETA":
                            status_pago_txt = "✅ Pago (Controle)" if item["pago"] else "⏳ Não Pago"
                            st.write(f"📱 **{item['coletor']}** | R$ {item['valor']:.2f} | Data: {item['data']} ({status_pago_txt})")
                        else:
                            st.write(f"🏅 **{item['coletor']}** | R$ {item['valor']:.2f} | Data: {item['data']} ({item['detalhe']})")
                    with col_p2:
                        if item["tipo"] == "COLETA" and not item["pago"]:
                            if st.button(f"Marcar como Pago", key=f"pag_{item['id']}"):
                                with st.spinner("Atualizando..."):
                                    supabase.table("coletas").update({"pago": True}).eq("id", item["id"]).execute()
                                st.rerun()
                        elif item["tipo"] == "PREMIACAO":
                            st.caption("✨ Lançamento de Premiação")
                    st.markdown("---")

        # ----------------- ABA 2: REGISTRAR/VER VALES -----------------
        with sub_menu_adm[1]:
            st.subheader("💰 Registrar Vale / Adiantamento")
            coletores_vales = [u["nome_completo"] for u in res_users_data if u.get("cargo") == "COLETOR"]
            
            if coletores_vales:
                coletor_vale = st.selectbox("Selecione o Coletor para o Vale:", coletores_vales, key=f"sel_vale_{st.session_state['reset_ctr']}")
                valor_vale_input = st.number_input("Valor do Adiantamento (R$):", min_value=1.0, step=5.0, value=10.0, key=f"val_vale_{st.session_state['reset_ctr']}")
                data_vale = st.date_input("Data do Vale:", obter_agora_brasilia().date(), key=f"dat_vale_{st.session_state['reset_ctr']}")
                motivo_vale = st.text_input("Observação/Motivo (Opcional):", value="Adiantamento de Coletas", key=f"mot_vale_{st.session_state['reset_ctr']}")
                
                foto_vale = st.file_uploader("Selecione ou tire a foto do comprovante do vale:", type=["png", "jpg", "jpeg"], key=f"foto_vale_{st.session_state['reset_ctr']}")
                
                if st.button("Lançar Vale", type="primary"):
                    if foto_vale:
                        try:
                            with st.spinner("Processando e compactando imagem do vale..."):
                                img = Image.open(foto_vale)
                                img.thumbnail((1024, 1024))
                                
                                buffer_memoria = BytesIO()
                                img.save(buffer_memoria, format="JPEG", quality=75, optimize=True)
                                conteudo_foto = buffer_memoria.getvalue()
                                
                                nome_foto_nuvem = f"vale_{obter_agora_brasilia().strftime('%Y%m%d%H%M%S')}_{st.session_state['usuario_atual']}.jpg"
                                
                                supabase.storage.from_("comprovantes").upload(
                                    path=nome_foto_nuvem, file=conteudo_foto,
                                    file_options={"content-type": "image/jpeg"}
                                )
                                
                                foto_url_final = supabase.storage.from_("comprovantes").get_public_url(nome_foto_nuvem)
                                
                                novo_vale = {
                                    "data": str(data_vale), "coletor": str(coletor_vale).strip(),
                                    "valor_vale": float(valor_vale_input), "descricao": str(motivo_vale).strip(),
                                    "foto_url": foto_url_final
                                }
                                with st.spinner("Salvando..."):
                                    supabase.table("vales_coleta").insert(novo_vale).execute()
                                st.success(f"✅ Vale de R$ {valor_vale_input:.2f} registrado com sucesso!")
                                st.session_state["reset_ctr"] += 1
                                st.rerun()
                        except Exception as vale_err:
                            st.error(f"⚠️ Erro ao salvar o vale no banco: {vale_err}")
                    else:
                        st.error("⚠️ Por favor, adicione a foto do comprovante do vale antes de lançar.")
            else:
                st.info("Nenhum coletor cadastrado para receber vales.")
                
            st.markdown("---")
            st.subheader("📋 Histórico de Vales Emitidos")
            
            st.markdown("#### 🔍 Filtrar Histórico de Vales")
            col_v1, col_v2, col_v3 = st.columns(3)
            with col_v1:
                v_data_ini = st.date_input("De (Vale):", value=st.session_state["v_adm_filtro_inicio"], key="v_adm_ini")
            with col_v2:
                v_data_fim = st.date_input("Até (Vale):", value=st.session_state["v_adm_filtro_fim"], key="v_adm_fim")
            with col_v3:
                coletor_vale_sel = st.selectbox("Filtrar por Coletor (Vales):", lista_coletores, key="v_adm_coletor_filtro")
            
            st.session_state["v_adm_filtro_inicio"] = v_data_ini
            st.session_state["v_adm_filtro_fim"] = v_data_fim
            
            if not df_bruto_vales.empty:
                df_bruto_vales['data_dt'] = pd.to_datetime(df_bruto_vales['data']).dt.date
                vales_filtrados_historico = df_bruto_vales[(df_bruto_vales['data_dt'] >= v_data_ini) & (df_bruto_vales['data_dt'] <= v_data_fim)].copy()
                if coletor_vale_sel != "Todos":
                    vales_filtrados_historico = vales_filtrados_historico[vales_filtrados_historico["coletor"] == coletor_vale_sel]
            else:
                vales_filtrados_historico = df_bruto_vales.copy()

            if vales_filtrados_historico.empty:
                st.info("Nenhum vale encontrado para os filtros selecionados.")
            else:
                st.metric("Total de Vales Listados", f"R$ {vales_filtrados_historico['valor_vale'].sum():.2f}")
                for idx, row in vales_filtrados_historico.sort_values(by="data", ascending=False).iterrows():
                    with st.expander(f"📉 Data: {row['data']} | Coletor: {row['coletor']} | Valor: R$ {float(row['valor_vale']):.2f}"):
                        st.write(f"**Descrição/Motivo:** {row['descricao']}")
                        link_foto_vale = extrair_url_valida(row.get('foto_url'))
                        if link_foto_vale:
                            st.image(link_foto_vale, width=200, caption="Comprovante do Vale")
                        else:
                            st.caption("⚠️ Sem comprovante visual anexado.")

        # ----------------- ABA 3: SERVIÇOS/PREMIAÇÕES -----------------
        with sub_menu_adm[2]:
            st.subheader("🏅 Registrar Serviço Extra / Premiação")
            coletores_premios = [u["nome_completo"] for u in res_users_data if u.get("cargo") == "COLETOR"]
            if coletores_premios:
                coletor_premio = st.selectbox("Selecione o Coletor:", coletores_premios, key=f"sel_premio_{st.session_state['reset_ctr']}")
                valor_premio_input = st.number_input("Valor da Premiação (R$):", min_value=1.0, step=5.0, value=50.0, key=f"val_premio_{st.session_state['reset_ctr']}")
                data_premio = st.date_input("Data do Lançamento:", obter_agora_brasilia().date(), key=f"dat_premio_{st.session_state['reset_ctr']}")
                motivo_premio = st.text_input("Descrição/Motivo:", value="Meta Atingida", key=f"mot_premio_{st.session_state['reset_ctr']}")
                
                if st.button("Lançar Premiação", type="primary"):
                    try:
                        nova_premio = {
                            "data": str(data_premio), "coletor": str(coletor_premio).strip(),
                            "valor_premiacao": float(valor_premio_input), "descricao": str(motivo_premio).strip()
                        }
                        with st.spinner("Salvando..."):
                            supabase.table("premiacoes").insert(nova_premio).execute()
                        st.success(f"✅ Premiação de R$ {valor_premio_input:.2f} registrada com sucesso!")
                        st.session_state["reset_ctr"] += 1
                        st.rerun()
                    except Exception as prem_err:
                        st.error(f"⚠️ Erro ao salvar premiação no banco: {prem_err}")
            else:
                st.info("Nenhum coletor cadastrado para receber premiações.")

        # ----------------- ABA 4: RELATÓRIO DE USO DOS COMPROVANTES -----------------
        with sub_menu_adm[3]:
            st.subheader("📊 Relatório de Auditoria: Envio de Comprovantes")
            st.markdown("Veja quem andou localizando e compartilhando comprovantes de ordens de serviço com os clientes:")
            
            try:
                resposta_logs = supabase.table("logs_comprovantes").select("*").order("data_hora", desc=True).limit(200).execute()
                dados_logs = resposta_logs.data
                
                if not dados_logs:
                    st.info("ℹ️ Nenhum registro de envio ou busca encontrado até o momento.")
                else:
                    df_logs = pd.DataFrame(dados_logs)
                    df_logs["Horário"] = pd.to_datetime(df_logs["data_hora"]).dt.tz_convert("America/Sao_Paulo").dt.strftime("%d/%m/%Y %H:%M:%S")
                    
                    df_logs_vitrine = df_logs[["Horário", "nome_completo", "termo_pesquisado", "os_encontrada"]].rename(
                        columns={
                            "nome_completo": "Coletor",
                            "termo_pesquisado": "Termo Buscado",
                            "os_encontrada": "OS Encontrada(s)"
                        }
                    )
                    st.dataframe(df_logs_vitrine, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Erro ao carregar o relatório do banco de dados: {e}")

        # ----------------- ABA 5: CADASTRO DE USUÁRIOS -----------------
        with sub_menu_adm[4]:
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
                        with st.spinner("Cadastrando..."):
                            supabase.table("usuarios").insert(novo_user_dict).execute()
                        st.cache_data.clear()
                        st.success(f"🎉 {novo_nome} cadastrado com sucesso!")
                        st.session_state["reset_ctr"] += 1
                        st.rerun()

    # =========================================================================
    # PERFIL COLETOR
    # =========================================================================
    else:
        with st.container():
            menu = st.tabs(["📲 Enviar Coleta", "📊 Minhas Coletas", "💰 Meus Vales", "📄 Comprovantes"], key="tabs_coletor_perfil")

        with menu[0]:
            st.header("Novo Envio")
            st.info(f"Registrando para: **{st.session_state['nome_completo_atual']}**")
            
            quantidade = st.number_input("Quantidade de aparelhos:", min_value=1, step=1, value=1, key=f"qtd_c_{st.session_state['reset_ctr']}")
            foto_comprovante = st.file_uploader("Selecione ou tire a foto do comprovante:", type=["png", "jpg", "jpeg"], key=f"foto_c_{st.session_state['reset_ctr']}")
                
            if st.button("Enviar para Aprovação", type="primary", use_container_width=True):
                if quantidade and foto_comprovante:
                    try:
                        with st.spinner("Processando imagem..."):
                            img = Image.open(foto_comprovante)
                            img.thumbnail((1024, 1024))
                            
                            buffer_memoria = BytesIO()
                            img.save(buffer_memoria, format="JPEG", quality=75, optimize=True)
                            conteudo_foto = buffer_memoria.getvalue()
                            
                            nome_foto_nuvem = f"{obter_agora_brasilia().strftime('%Y%m%d%H%M%S')}_{st.session_state['usuario_atual']}.jpg"
                            
                            supabase.storage.from_("comprovantes").upload(
                                path=nome_foto_nuvem, file=conteudo_foto,
                                file_options={"content-type": "image/jpeg"}
                            )
                            
                            foto_url_final = supabase.storage.from_("comprovantes").get_public_url(nome_foto_nuvem)
                            
                            novo_registro = {
                                "data": obter_agora_brasilia().strftime("%Y-%m-%d"), 
                                "coletor": st.session_state['nome_completo_atual'], 
                                "quantidade": int(quantidade),
                                "foto_url": foto_url_final, 
                                "status": "Pendente", 
                                "valor_total": round(float(quantidade * VALOR_POR_COLETA), 2),
                                "pago": False
                            }
                            
                            supabase.table("coletas").insert(novo_registro).execute()
                            st.success("✅ Envio realizado com sucesso!")
                            st.session_state["reset_ctr"] += 1
                            st.rerun()
                    except Exception as err:
                        st.error(f"⚠️ Erro no processo de envio: {err}")
                else:
                    st.error("⚠️ Por favor, adicione a foto antes de enviar.")

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
            
            total_coletas_c = 0.0
            total_premiacoes_c = 0.0
            total_vales_c = 0.0
            dados_coletor = pd.DataFrame()
            df_premiacoes_c = pd.DataFrame()
            df_vales = pd.DataFrame()
            
            try:
                res_coletas_c = supabase.table("coletas").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                df = pd.DataFrame(res_coletas_c.data) if res_coletas_c.data else pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
                if "pago" not in df.columns:
                    df["pago"] = False
                else:
                    df["pago"] = df["pago"].fillna(False)
            except Exception:
                df = pd.DataFrame(columns=["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"])
                
            df['data_dt'] = pd.to_datetime(df['data']).dt.date if not df.empty else None
            dados_coletor = df[(df['data_dt'] >= c_data_ini) & (df['data_dt'] <= c_data_fim)] if not df.empty else pd.DataFrame()
            
            try:
                res_premiacoes_c = supabase.table("premiacoes").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                df_premiacoes_c = pd.DataFrame(res_premiacoes_c.data) if res_premiacoes_c.data else pd.DataFrame(columns=["data", "valor_premiacao", "descricao"])
            except Exception:
                df_premiacoes_c = pd.DataFrame(columns=["data", "valor_premiacao", "descricao"])
            
            df_premiacoes_c['data_dt'] = pd.to_datetime(df_premiacoes_c['data']).dt.date if not df_premiacoes_c.empty else None
            premiacoes_dele_filtrado = df_premiacoes_c[(df_premiacoes_c['data_dt'] >= c_data_ini) & (df_premiacoes_c['data_dt'] <= c_data_fim)] if not df_premiacoes_c.empty else pd.DataFrame()
            total_premiacoes_c = float(premiacoes_dele_filtrado["valor_premiacao"].sum()) if not premiacoes_dele_filtrado.empty else 0.0

            try:
                res_vales_c = supabase.table("vales_coleta").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                df_vales = pd.DataFrame(res_vales_c.data) if res_vales_c.data else pd.DataFrame(columns=["data", "valor_vale"])
            except Exception:
                df_vales = pd.DataFrame(columns=["data", "valor_vale"])
                
            if not df_vales.empty:
                df_vales['data_dt'] = pd.to_datetime(df_vales['data']).dt.date
                total_vales_c = float(df_vales[(df_vales['data_dt'] >= c_data_ini) & (df_vales['data_dt'] <= c_data_fim)]["valor_vale"].sum())
            else:
                total_vales_c = 0.0
            
            aprovadas = dados_coletor[dados_coletor["status"] == "Aprovado"] if not dados_coletor.empty else pd.DataFrame()
            total_coletas_c = float(aprovadas["valor_total"].sum()) if not aprovadas.empty else 0.0
            
            total_liquido_coletor = (total_coletas_c + total_premiacoes_c) - total_vales_c
            
            cm1, cm2, cm3, cm4 = st.columns(4)
            cm1.metric("Bruto Aparelhos", f"R$ {total_coletas_c:.2f}")
            cm2.metric("Premiações (+)", f"R$ {total_premiacoes_c:.2f}")
            cm3.metric("Vales (-)", f"R$ {total_vales_c:.2f}")
            cm4.metric("Líquido a Pagar", f"R$ {total_liquido_coletor:.2f}")
            
            st.markdown("### Envios do Período")
            
            lista_expander = []
            if not dados_coletor.empty:
                for idx, row in dados_coletor.iterrows():
                    lista_expander.append({
                        "tipo": "COLETA", "data": row['data'], "quantidade": row['quantidade'],
                        "status": row['status'], "pago": row.get('pago'), "valor_total": row['valor_total'],
                        "foto_url": row.get('foto_url'), "descricao": ""
                    })
            if not premiacoes_dele_filtrado.empty:
                for idx, row in premiacoes_dele_filtrado.iterrows():
                    lista_expander.append({
                        "tipo": "PREMIACAO", "data": row['data'], "quantidade": 1,
                        "status": "Aprovado", "pago": False, "valor_total": row['valor_premiacao'],
                        "foto_url": None, "descricao": row['descricao']
                    })
                    
            if not lista_expander:
                st.info("Nenhuma movimentação encontrada.")
            else:
                lista_expander_ordenada = sorted(lista_expander, key=lambda x: x['data'], reverse=True)
                for item in lista_expander_ordenada:
                    if item["tipo"] == "PREMIACAO":
                        with st.expander(f"🏅 Data: {item['data']} | Serviço Extra / Premiação"):
                            st.write(f"**Valor:** R$ {float(item['valor_total']):.2f}")
                            st.write(f"**Descrição:** {item['descricao']}")
                    else:
                        status_cor = "🟢" if item['status'] == "Aprovado" else "🟡" if item['status'] == "Pendente" else "🔴"
                        status_pago_txt = "✅ Enviado/Pago" if item['pago'] == True else "⏳ Aguardando Acerto"
                        
                        if item['status'] == "Recusado":
                            with st.expander(f"🔴 Data: {item['data']} | Qtd: {item['quantidade']} | REPROVADA"):
                                st.write("❌ Esta solicitação foi recusada pela gerência.")
                        else:
                            with st.expander(f"{status_cor} Data: {item['data']} | Qtd: {item['quantidade']} | {status_pago_txt}"):
                                st.write(f"**Valor:** R$ {float(item['valor_total']):.2f}")
                                link_foto = extrair_url_valida(item['foto_url'])
                                if link_foto: 
                                    st.image(link_foto, width=150)
                                else:
                                    st.caption("📷 Sem foto anexada")

        with menu[2]:
            st.header("Meus Adiantamentos (Vales)")
            try:
                res_vales_c2 = supabase.table("vales_coleta").select("*").eq("coletor", st.session_state['nome_completo_atual']).execute()
                df_v = pd.DataFrame(res_vales_c2.data) if res_vales_c2.data else pd.DataFrame(columns=["data", "valor_vale", "descricao", "foto_url"])
            except Exception:
                df_v = pd.DataFrame(columns=["data", "valor_vale", "descricao", "foto_url"])
                
            if df_v.empty:
                st.info("Nenhum vale registrado.")
            else:
                df_v['data_dt'] = pd.to_datetime(df_v['data']).dt.date
                vales_coletor = df_v[(df_v['data_dt'] >= st.session_state["c_filtro_inicio"]) & (df_v['data_dt'] <= st.session_state["c_filtro_fim"])]
                
                if vales_coletor.empty:
                    st.info("Nenhum vale registrado para o período.")
                else:
                    st.metric("Total em Vales no Período", f"R$ {vales_coletor['valor_vale'].sum():.2f}")
                    for idx, row in vales_coletor.sort_values(by="data", ascending=False).iterrows():
                        with st.expander(f"📉 Data: {row['data']} | Valor: R$ {float(row['valor_vale']):.2f}"):
                            st.write(f"**Descrição:** {row['descricao']}")
                            link_foto_vale_c = extrair_url_valida(row.get('foto_url'))
                            if link_foto_vale_c:
                                st.image(link_foto_vale_c, width=180, caption="Comprovante do Adiantamento")

        with menu[3]:
            st.subheader("🔍 Localizar Comprovante do Cliente")
            termo_busca = st.text_input("Digite a OS ou Nome do Cliente:", placeholder="Ex: 10542...").strip()
            
            if termo_busca:
                try:
                    resposta = supabase.table("comprovantes_clientes").select("*").or_(f"cliente.ilike.%{termo_busca}%,ordem_servico.ilike.%{termo_busca}%").order("data_emissao", desc=True).execute()
                    dados = resposta.data
                    
                    if not dados:
                        st.info("ℹ️ Nenhum comprovante encontrado.")
                    else:
                        st.success(f"🎉 Encontrado(s) {len(dados)} item(ns):")
                        
                        # Monitoramento interno silencioso
                        lista_os_encontradas = ", ".join([str(reg['ordem_servico']) for reg in dados])
                        registro_log = {
                            "usuario": st.session_state["usuario_atual"],
                            "nome_completo": st.session_state["nome_completo_atual"],
                            "termo_pesquisado": termo_busca,
                            "os_encontrada": lista_os_encontradas
                        }
                        supabase.table("logs_comprovantes").insert(registro_log).execute()
                        
                        for registro in dados:
                            with st.container():
                                st.markdown(f"### 📋 OS: {registro['ordem_servico']}")
                                st.markdown(f"**👤 Cliente:** {registro['cliente']}")
                                data_formatada = datetime.strptime(registro['data_emissao'], '%Y-%m-%d').strftime('%d/%m/%Y')
                                st.markdown(f"**📅 Emissão:** {data_formatada}")
                                
                                url_comprovante = registro['arquivo_url']
                                col_b1, col_b2 = st.columns(2)
                                with col_b1:
                                    st.link_button("📥 Abrir PDF", url_comprovante, use_container_width=True)
                                with col_b2:
                                    mensagem_zap = f"Olá! Segue o seu comprovante de coleta referente à *OS {registro['ordem_servico']}*.\n\n🔗 Link:\n{url_comprovante}"
                                    link_whatsapp = f"https://api.whatsapp.com/send?text={urllib.parse.quote(mensagem_zap)}"
                                    st.link_button("🟢 Enviar WhatsApp", link_whatsapp, use_container_width=True)
                            st.markdown("---")
                except Exception as e:
                    st.error(f"Erro na base de dados: {e}")