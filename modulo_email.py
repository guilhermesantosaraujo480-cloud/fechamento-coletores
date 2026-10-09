import streamlit as st
import pandas as pd
import time
import random
import smtplib
from email.message import EmailMessage
from datetime import datetime
import urllib.parse
from io import BytesIO

# --- TEMPLATE HTML DO E-MAIL ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { margin: 0; padding: 0; background-color: #f4f5f7; font-family: 'Segoe UI', Arial, sans-serif; color: #333333; }
        .email-container { max-width: 600px; margin: 30px auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .header-banner { background-color: #ffffff; padding: 30px 30px 15px 30px; text-align: left; border-bottom: 1px solid #f0f0f0; }
        .logo-text { font-size: 26px; font-weight: bold; color: #660099; letter-spacing: -0.5px; }
        .logo-text span { color: #333333; font-weight: normal; font-size: 22px; }
        .content-body { padding: 30px; text-align: left; }
        .headline { font-size: 22px; font-weight: 700; margin-bottom: 15px; color: #660099; }
        .message-text { font-size: 15px; line-height: 1.6; margin-bottom: 25px; color: #444444; }
        .purple-card { background-color: #660099; border-radius: 10px; padding: 25px; margin: 25px 0; color: #ffffff; }
        .purple-card h2 { margin: 0 0 10px 0; font-size: 18px; color: #ffffff; font-weight: 600; }
        .purple-card p { margin: 0 0 20px 0; font-size: 14px; color: #f3e6ff; line-height: 1.5; }
        .address-box { background-color: #f8f0ff; border-left: 4px solid #660099; padding: 15px; margin: 20px 0; border-radius: 0 8px 8px 0; }
        .address-box p { margin: 0; font-size: 14px; color: #333333; line-height: 1.5; }
        .btn-container { text-align: center; margin-top: 15px; }
        .btn-link { display: inline-block; background-color: #ffffff; color: #660099 !important; text-decoration: none; font-size: 14px; font-weight: bold; padding: 14px 32px; border-radius: 25px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-transform: uppercase; }
        .features-box { background-color: #f9f9fb; border: 1px solid #e9e9ee; border-radius: 8px; padding: 18px; margin-top: 25px; }
        .features-box p { margin: 0; font-size: 13px; line-height: 1.5; color: #666666; }
        .footer { background-color: #ffffff; padding: 25px 30px; font-size: 11px; color: #888888; text-align: center; border-top: 1px solid #f0f0f0; line-height: 1.5; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header-banner">
            <div class="logo-text">vivo <span>Retirada</span></div>
        </div>
        <div class="content-body">
            <div class="headline">Olá, {nome}!</div>
            <div class="message-text">{texto_dinamico}</div>
            <div class="address-box">
                <p><strong>📍 Endereço para retirada registrado no sistema:</strong></p>
                <p style="margin-top: 6px; color: #660099; font-weight: bold;">{endereco_completo_cliente}</p>
            </div>
            <div class="purple-card">
                <h2>CONFIRMAR NO WHATSAPP</h2>
                <p>Confirme se o endereço está correto para agendarmos o horário da coleta do equipamento.</p>
                <div class="btn-container">
                    <a href="{whatsapp_link}" target="_blank" class="btn-link">CONFIRMAR ENDEREÇO</a>
                </div>
            </div>
            <div class="features-box">
                <p style="font-weight: bold; color: #333333; margin-bottom: 5px;">⚠️ Informações Importantes:</p>
                <p>{regras_coleta}</p>
            </div>
            <p style="font-size: 14px; margin-top: 30px; color: #555555;">
                Atenciosamente,<br>
                <strong style="color: #660099;">Parceiro VIVO</strong>
            </p>
        </div>
        <div class="footer">
            Este é um e-mail automático enviado pelo sistema de logística. Por favor, não responda a esta mensagem.<br>
            © Telefônica Brasil S.A. Av. Engenheiro Luís Carlos Berrini, 1.376 - São Paulo/SP
        </div>
    </div>
</body>
</html>
"""

def obter_textos_modelo_1(tipo_cancelamento, protocolo):
    if tipo_cancelamento == "voluntario":
        texto = f"Como você solicitou o desligamento do seu plano Vivo, precisamos prosseguir com a etapa final do processo: a devolução dos equipamentos que estão sob sua responsabilidade. O recolhimento está associado ao protocolo #{protocolo}."
    elif tipo_cancelamento == "involuntario":
        texto = f"Identificamos o encerramento do seu sinal por iniciativa da Vivo. Para evitar multas contratuais adicionais que podem passar de <b>R$ 385 por equipamento</b> retido, precisamos recolher o roteador e modem vinculados ao protocolo #{protocolo}."
    else:
        texto = f"Seu contrato da Vivo foi encerrado recentemente. Para finalizar a baixa no sistema, precisamos realizar o recolhimento dos equipamentos vinculados ao protocolo #{protocolo}."
    
    regras = "Deixe o roteador e a fonte separados. Caso você tenha rotina corrida, os aparelhos podem ser deixados na portaria do prédio ou com algum vizinho/parente avisado."
    texto_whats = f"Olá! Vim pelo e-mail do protocolo {protocolo}. Quero confirmar meu endereço para a coleta técnica."
    return texto, regras, texto_whats

def obter_textos_modelo_2(protocolo):
    texto = f"<b>AVISO IMPORTANTE DE LOGÍSTICA:</b> Nossa equipe técnica parceira da Vivo estará passando na sua região no <b>período comercial (08:00 às 18:00)</b> para efetuar a retirada do aparelho modem/roteador referente ao protocolo #{protocolo}."
    regras = "• Deixe o roteador junto com a fonte (se perdeu a fonte, nos avise).<br>• <b>Apartamentos:</b> Pode deixar direto na portaria.<br>• Se você mudou de local, use o botão acima imediatamente para atualizar o endereço no WhatsApp."
    texto_whats = f"Olá! Recebi o aviso de rota para o protocolo {protocolo}. Quero dar meu 'ok' sobre o endereço cadastrado."
    return texto, regras, texto_whats

def carregar_dataframe_inteligente(arquivo):
    nome = arquivo.name.lower()
    if nome.endswith(".xlsx") or nome.endswith(".xls"):
        try:
            return pd.read_excel(arquivo)
        except Exception:
            arquivo.seek(0)
            return pd.read_csv(arquivo, sep='\t', encoding='latin1')
    
    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
    separadores = [None, '\t', ';', ',']
    
    for enc in encodings:
        for sep in separadores:
            try:
                arquivo.seek(0)
                if sep is None:
                    df = pd.read_csv(arquivo, sep=None, engine='python', encoding=enc)
                else:
                    df = pd.read_csv(arquivo, sep=sep, encoding=enc)
                if len(df.columns) > 1 and len(df) > 0:
                    return df
            except Exception:
                continue
    arquivo.seek(0)
    return pd.read_csv(arquivo, on_bad_lines='skip')


# --- INTERFACE DO STREAMLIT ---
def renderizar_aba_disparador_emails(supabase_client):
    st.subheader("📧 Disparador Automático de E-mails")

    # -------------------------------------------------------------
    # BLOCO DE MÉTRICAS DE CLIQUES (CORRIGIDO PARA EXECUTAR DENTRO DA ABA)
    # -------------------------------------------------------------
    st.markdown("### 📊 Métricas de Engajamento (Cliques no WhatsApp)")
    col_met1, col_met2 = st.columns([3, 1])
    with col_met2:
        if st.button("🔄 Atualizar Cliques"):
            st.rerun()

    try:
        res_cliques = supabase_client.table("cliques_email").select("*").execute()
        if res_cliques.data:
            df_cliques = pd.DataFrame(res_cliques.data)
            total_cliques = len(df_cliques)
            clientes_unicos = df_cliques["envio_id"].nunique() if "envio_id" in df_cliques.columns else total_cliques
            
            c1, c2 = st.columns(2)
            c1.metric("Total de Cliques Registrados", total_cliques)
            c2.metric("Clientes Únicos que Clicaram", clientes_unicos)
            
            with st.expander("🔍 Ver Detalhes dos Cliques"):
                st.dataframe(
                    df_cliques,
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.info("Nenhum clique registrado até o momento.")
    except Exception as e:
        st.error(f"Erro ao carregar métricas de clique: {e}")

    st.markdown("---")

    sub_tab1, sub_tab2 = st.tabs(["🚀 Realizar Disparos", "🔑 Gerenciar Contas Remetentes"])

    # -------------------------------------------------------------
    # TAB 1: GERENCIAR CONTAS REMETENTES
    # -------------------------------------------------------------
    with sub_tab2:
        st.markdown("### Cadastrar Nova Conta de E-mail (Chave de Acesso)")
        with st.form("form_nova_conta", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                novo_email = st.text_input("E-mail Remetente (ex: conta@gmail.com)").strip().lower()
                nome_rem = st.text_input("Nome de Exibição", value="Parceiro VIVO").strip()
            with col_b:
                nova_senha = st.text_input("Senha de App / Chave de Acesso", type="password").strip()
                limite_d = st.number_input("Limite Diário de Envios", min_value=10, max_value=2000, value=100)
            
            if st.form_submit_button("➕ Salvar Conta", type="primary"):
                if novo_email and nova_senha:
                    try:
                        supabase_client.table("contas_email").insert({
                            "email": novo_email,
                            "senha_app": nova_senha,
                            "nome_remetente": nome_rem,
                            "limite_diario": limite_d,
                            "ativa": True
                        }).execute()
                        st.success(f"✅ Conta {novo_email} cadastrada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao cadastrar conta: {e}")
                else:
                    st.warning("Preencha e-mail e senha de app.")

        st.markdown("---")
        st.markdown("### Contas Cadastradas")
        try:
            res_contas = supabase_client.table("contas_email").select("*").execute()
            dados_contas = res_contas.data
            if dados_contas:
                df_c = pd.DataFrame(dados_contas)
                for idx, r in df_c.iterrows():
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                    c1.write(f"📧 **{r['email']}** ({r['nome_remetente']})")
                    c2.write(f"Limite: {r['limite_diario']}/dia")
                    status_str = "🟢 Ativa" if r['ativa'] else "🔴 Inativa"
                    c3.write(f"Status: {status_str}")
                    
                    btn_txt = "Desativar" if r['ativa'] else "Ativar"
                    if c4.button(btn_txt, key=f"tog_{r['id']}"):
                        supabase_client.table("contas_email").update({"ativa": not r['ativa']}).eq("id", r['id']).execute()
                        st.rerun()
            else:
                st.info("Nenhuma conta registrada ainda.")
        except Exception as e:
            st.error(f"Erro ao listar contas: {e}")

    # -------------------------------------------------------------
    # TAB 2: DISPARAR E-MAILS
    # -------------------------------------------------------------
    with sub_tab1:
        res_ativas = supabase_client.table("contas_email").select("*").eq("ativa", True).execute()
        contas_ativas = res_ativas.data if res_ativas.data else []

        if not contas_ativas:
            st.warning("⚠️ Nenhuma conta de e-mail ativa encontrada. Cadastre e ative pelo menos uma conta na aba 'Gerenciar Contas'.")
            return

        st.info(f"✅ **{len(contas_ativas)} conta(s) ativa(s)** disponível(is) para rotação automática de disparos.")

        arquivo = st.file_uploader("📂 Faça upload da planilha (.xlsx, .xls, .csv ou .txt)", type=["xlsx", "xls", "csv", "txt"])
        
        if arquivo:
            try:
                df = carregar_dataframe_inteligente(arquivo)
                df = df.dropna(how='all')
                df.columns = [str(col).strip() for col in df.columns]
                st.success(f"📋 Planilha carregada com sucesso: **{len(df)} registros encontrados**.")
                with st.expander("👁️ Ver prévia da planilha carregada"):
                    st.dataframe(df.head(5), use_container_width=True)
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")
                return

            st.markdown("---")
            st.markdown("### Configurações da Campanha")

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                modelo_opcao = st.selectbox(
                    "Selecione o Modelo do E-mail:",
                    ["[1] Cancelamento (Voluntário/Involuntário + Multa)", "[2] Comunicado Urgente (Rota Técnica)"]
                )
                num_whatsapp = st.text_input("Número do WhatsApp de Destino:", value="5511921476792")

            with col_m2:
                delay_min = st.number_input("Delay Mínimo (segundos):", min_value=1, max_value=60, value=4)
                delay_max = st.number_input("Delay Máximo (segundos):", min_value=1, max_value=60, value=8)

            st.markdown("---")

            # BOTÕES DE CONTROLE DOS DISPAROS (INICIAR E PARAR)
            if "parar_disparo" not in st.session_state:
                st.session_state["parar_disparo"] = False

            col_btn_start, col_btn_stop = st.columns([3, 1])
            with col_btn_stop:
                if st.button("🛑 PARAR DISPARO", type="secondary", use_container_width=True):
                    st.session_state["parar_disparo"] = True

            iniciar = col_btn_start.button("🚀 Iniciar Disparos em Massa", type="primary", use_container_width=True)

            if iniciar:
                st.session_state["parar_disparo"] = False
                barra = st.progress(0)
                status_txt = st.empty()

                lista_status = []
                lista_horarios = []

                total_reg = len(df)
                sucessos = 0
                erros = 0
                ignorados = 0

                emails_invalidos_lista = [
                    'email@email.com', 'teste@teste.com', 'naotem@naotem.com', 
                    'sememail@sememail.com', 'cliente@cliente.com', 'xxx@xxx.com'
                ]

                for i, row in df.iterrows():
                    # VERIFICA SE O BOTÃO DE PARAR FOI CLICADO
                    if st.session_state["parar_disparo"]:
                        st.warning(f"⚠️ Disparo cancelado pelo usuário! Interrompido no registro {i}/{total_reg}.")
                        st.session_state["parar_disparo"] = False
                        break

                    conta_atual = contas_ativas[i % len(contas_ativas)]
                    meu_email = conta_atual["email"]
                    minha_senha = conta_atual["senha_app"]

                    email_cliente = str(row.get('Email') or row.get('email') or '').strip().lower()
                    nome_cliente = str(row.get('Cliente') or row.get('nome') or 'Cliente').strip()
                    protocolo_cliente = str(row.get('BA') or row.get('protocolo') or '').strip()

                    rua = str(row.get('Endereço') or row.get('endereço') or row.get('endereco') or '').strip()
                    numero = str(row.get('Número') or row.get('número') or row.get('numero') or '').strip()
                    bairro = str(row.get('Bairro') or row.get('bairro') or '').strip()
                    cep = str(row.get('Cep') or row.get('cep') or '').strip()

                    partes_end = []
                    if rua: partes_end.append(rua)
                    if numero: partes_end.append(f"Nº {numero}")
                    if bairro: partes_end.append(bairro)
                    if cep: partes_end.append(f"CEP: {cep}")
                    endereco_completo = " - ".join(partes_end) if partes_end else "Endereço incompleto na planilha"

                    tipo_bruto = str(row.get('Tipo') or row.get('tipo') or row.get('tipo_cancelamento') or 'padrao').strip().lower()
                    if "volunt" in tipo_bruto and "involunt" not in tipo_bruto:
                        tipo_canc = "voluntario"
                    elif "involunt" in tipo_bruto:
                        tipo_canc = "involuntario"
                    else:
                        tipo_canc = "padrao"

                    if ("@" not in email_cliente or 
                        "." not in email_cliente or 
                        email_cliente in emails_invalidos_lista or 
                        email_cliente.startswith("email@")):
                        
                        lista_status.append("IGNORADO: E-mail fictício/inválido")
                        lista_horarios.append(datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
                        ignorados += 1
                        barra.progress((i + 1) / total_reg)
                        continue

                    status_txt.text(f"Enviando {i+1}/{total_reg} para {email_cliente} via [{meu_email}]...")

                    if "[1]" in modelo_opcao:
                        texto_din, regras, texto_w = obter_textos_modelo_1(tipo_canc, protocolo_cliente)
                    else:
                        texto_din, regras, texto_w = obter_textos_modelo_2(protocolo_cliente)

                    titulos = [
                        f"Atualização de agendamento: Protocolo {protocolo_cliente}",
                        f"Ordem de coleta técnica gerada - Ref: {protocolo_cliente}",
                        f"Informações sobre a retirada do equipamento (Protocolo {protocolo_cliente})",
                        f"{nome_cliente}, agendamento de coleta pendente - Protocolo {protocolo_cliente}",
                        f"Logística Vivo: Confirmação de atendimento para {nome_cliente}",
                        f"Retirada técnica agendada para {nome_cliente} (Ref: {protocolo_cliente})",
                        f"Setor de Logística - Solicitação de atendimento {protocolo_cliente}",
                        f"Suporte Técnico: Procedimento de devolução de aparelho {protocolo_cliente}",
                        f"Aviso sobre o recolhimento de equipamento técnico #{protocolo_cliente}",
                        f"Instruções para encerramento de ordem de serviço: {protocolo_cliente}"
                    ]
                    assunto = random.choice(titulos)

                    # LINK DO WHATSAPP RASTREÁVEL
                    texto_w_completo = f"{texto_w} Meu endereço cadastrado é: {endereco_completo}"
                    link_wa_direto = f"https://api.whatsapp.com/send?phone={num_whatsapp}&text={urllib.parse.quote(texto_w_completo)}"
                    
                    url_supabase_function = "https://jyymqbvgehhhlaanltlz.supabase.co/functions/v1/super-function"
                    link_w = f"{url_supabase_function}?protocolo={protocolo_cliente}&dest={urllib.parse.quote(link_wa_direto)}"

                    try:
                        msg = EmailMessage()
                        msg['Subject'] = assunto
                        msg['From'] = meu_email
                        msg['To'] = email_cliente

                        html_corpo = HTML_TEMPLATE.format(
                            nome=nome_cliente,
                            texto_dinamico=texto_din,
                            endereco_completo_cliente=endereco_completo,
                            regras_coleta=regras,
                            whatsapp_link=link_w
                        )
                        msg.set_content(html_corpo, subtype='html')

                        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                            smtp.login(meu_email, minha_senha)
                            smtp.send_message(msg)

                        sucessos += 1
                        lista_status.append(f"Sucesso (via {meu_email})")
                        lista_horarios.append(datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
                    except Exception as err:
                        erros += 1
                        lista_status.append(f"Erro: {err}")
                        lista_horarios.append(datetime.now().strftime('%d/%m/%Y %H:%M:%S'))

                    barra.progress((i + 1) / total_reg)
                    time.sleep(random.randint(delay_min, delay_max))

                st.success(f"🎉 Processo concluído! Sucessos: {sucessos} | Ignorados: {ignorados} | Erros: {erros}")

                df['status_envio'] = lista_status
                df['data_hora'] = lista_horarios

                buffer_rel = BytesIO()
                with pd.ExcelWriter(buffer_rel, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Resultado')
                buffer_rel.seek(0)

                st.download_button(
                    label="📊 Baixar Relatório do Disparo (.xlsx)",
                    data=buffer_rel,
                    file_name=f"relatorio_disparos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )