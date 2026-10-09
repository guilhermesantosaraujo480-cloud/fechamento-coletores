import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import time
import random
import re
import html
import json
import uuid
import smtplib
import urllib.parse
import requests
from email.message import EmailMessage
from email.utils import formataddr
from datetime import datetime, timedelta, timezone
from io import BytesIO

try:
    from cryptography.fernet import Fernet
    CRIPTO_OK = True
except Exception:
    CRIPTO_OK = False

FUSO_BR = timezone(timedelta(hours=-3))
PREFIXO_CRIPTO = "enc:"
LIMITE_MAXIMO_POR_CONTA = 500          # teto do Gmail comum; use bem menos em contas novas
MAX_ERROS_SEGUIDOS = 5                 # aborta a campanha se der erro em sequência
REGRAS_PADRAO = "Deixe o roteador e a fonte separados. Se preferir, pode deixar na portaria do prédio."
WHATS_PADRAO = "Olá! Vim pelo e-mail do protocolo {protocolo}. Quero confirmar meu endereço para a coleta."

# --- TEMPLATE HTML DO E-MAIL ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ margin: 0; padding: 0; background-color: #f4f5f7; font-family: 'Segoe UI', Arial, sans-serif; color: #333333; }}
        .email-container {{ max-width: 600px; margin: 30px auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
        .header-banner {{ background-color: #ffffff; padding: 30px 30px 15px 30px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
        .logo-text {{ font-size: 24px; font-weight: bold; color: #660099; letter-spacing: -0.5px; }}
        .logo-text span {{ color: #333333; font-weight: normal; font-size: 18px; }}
        .content-body {{ padding: 30px; text-align: left; }}
        .headline {{ font-size: 22px; font-weight: 700; margin-bottom: 15px; color: #660099; }}
        .message-text {{ font-size: 15px; line-height: 1.6; margin-bottom: 25px; color: #444444; }}
        .purple-card {{ background-color: #660099; border-radius: 10px; padding: 25px; margin: 25px 0; color: #ffffff; }}
        .purple-card h2 {{ margin: 0 0 10px 0; font-size: 18px; color: #ffffff; font-weight: 600; }}
        .purple-card p {{ margin: 0 0 20px 0; font-size: 14px; color: #f3e6ff; line-height: 1.5; }}
        .address-box {{ background-color: #f8f0ff; border-left: 4px solid #660099; padding: 15px; margin: 20px 0; border-radius: 0 8px 8px 0; }}
        .address-box p {{ margin: 0; font-size: 14px; color: #333333; line-height: 1.5; }}
        .btn-container {{ text-align: center; margin-top: 15px; }}
        .btn-link {{ display: inline-block; background-color: #ffffff; color: #660099 !important; text-decoration: none; font-size: 14px; font-weight: bold; padding: 14px 32px; border-radius: 25px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-transform: uppercase; }}
        .features-box {{ background-color: #f9f9fb; border: 1px solid #e9e9ee; border-radius: 8px; padding: 18px; margin-top: 25px; }}
        .features-box p {{ margin: 0; font-size: 13px; line-height: 1.5; color: #666666; }}
        .footer {{ background-color: #ffffff; padding: 25px 30px; font-size: 11px; color: #888888; text-align: center; border-top: 1px solid #f0f0f0; line-height: 1.5; }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header-banner">
            <div class="logo-text">{empresa} <span>Retirada de equipamento</span></div>
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
                <strong style="color: #660099;">{empresa}</strong>
            </p>
        </div>
        <div class="footer">
            Enviado por <strong>{empresa}</strong>. {identificacao}<br>
            Você recebeu esta mensagem porque há um equipamento pendente de devolução vinculado ao seu cadastro.
            Para não receber mais mensagens, responda este e-mail com a palavra <strong>SAIR</strong>.
        </div>
    </div>
</body>
</html>
"""


# =============================================================================
# UTILITÁRIOS
# =============================================================================
def cfg(chave, padrao=""):
    """Lê uma configuração do st.secrets sem quebrar se não existir."""
    try:
        valor = st.secrets.get(chave, padrao)
        return valor if valor is not None else padrao
    except Exception:
        return padrao


def esc(texto):
    return html.escape(str(texto), quote=True)


def agora_br():
    return datetime.now(FUSO_BR)


def agora_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def inicio_do_dia_utc_iso():
    ini = agora_br().replace(hour=0, minute=0, second=0, microsecond=0)
    return ini.astimezone(timezone.utc).isoformat()


def pegar(row, *chaves, padrao=""):
    """Pega o primeiro valor preenchido da linha (ignora maiúsculas e NaN/vazios)."""
    mapa = {str(c).strip().lower(): c for c in row.index}
    for chave in chaves:
        col = mapa.get(chave.lower())
        if col is None:
            continue
        valor = row[col]
        if pd.isna(valor):
            continue
        s = str(valor).strip()
        if s and s.lower() not in ("nan", "none", "null"):
            if re.fullmatch(r"\d+\.0", s):  # 123.0 -> 123
                s = s[:-2]
            return s
    return padrao


EMAILS_FICTICIOS = {
    "email@email.com", "teste@teste.com", "naotem@naotem.com",
    "sememail@sememail.com", "cliente@cliente.com", "xxx@xxx.com",
}


def email_valido(email):
    if not email or email in EMAILS_FICTICIOS or email.startswith("email@"):
        return False
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is not None


def html_para_texto(s):
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def buscar_todos(sb, tabela, colunas="*", filtros=None, gte=None, ordem="id", tamanho=1000, maximo=100000):
    """Busca paginada (o Supabase devolve no máximo 1000 linhas por consulta)."""
    resultado, inicio = [], 0
    while inicio < maximo:
        q = sb.table(tabela).select(colunas)
        for col, val in (filtros or {}).items():
            q = q.eq(col, val)
        if gte:
            q = q.gte(gte[0], gte[1])
        dados = q.order(ordem).range(inicio, inicio + tamanho - 1).execute().data or []
        resultado.extend(dados)
        if len(dados) < tamanho:
            break
        inicio += tamanho
    return resultado


# =============================================================================
# CRIPTOGRAFIA DAS SENHAS DE APP (chave fica nos secrets, não no banco)
# =============================================================================
def _fernet():
    chave = cfg("CHAVE_CRIPTO")
    if not (CRIPTO_OK and chave):
        return None
    try:
        return Fernet(str(chave).encode())
    except Exception:
        return None


def proteger_senha(senha):
    f = _fernet()
    if f is None:
        return senha
    return PREFIXO_CRIPTO + f.encrypt(senha.encode()).decode()


def revelar_senha(valor):
    if not valor:
        return ""
    if not str(valor).startswith(PREFIXO_CRIPTO):
        return str(valor)  # senha antiga, ainda em texto puro
    f = _fernet()
    if f is None:
        return ""
    try:
        return f.decrypt(str(valor)[len(PREFIXO_CRIPTO):].encode()).decode()
    except Exception:
        return ""


# =============================================================================
# MODELOS DE E-MAIL
# =============================================================================
def conteudo_padrao_1(tipo, protocolo_h, ctx):
    if tipo == "voluntario":
        texto = (f"Como você solicitou o desligamento do seu plano, precisamos prosseguir com a etapa final do processo: "
                 f"a devolução dos equipamentos que estão sob sua responsabilidade. "
                 f"O recolhimento está associado ao protocolo #{protocolo_h}.")
    elif tipo == "involuntario":
        if ctx["valor_multa"]:
            trecho = f"multas contratuais adicionais de até <b>{esc(ctx['valor_multa'])} por equipamento</b> retido"
        else:
            trecho = "cobranças adicionais por equipamento retido"
        texto = (f"Identificamos o encerramento do seu sinal por iniciativa da operadora. Para evitar {trecho}, "
                 f"precisamos recolher o roteador e modem vinculados ao protocolo #{protocolo_h}.")
    else:
        texto = (f"Seu contrato foi encerrado recentemente. Para finalizar a baixa no sistema, precisamos realizar "
                 f"o recolhimento dos equipamentos vinculados ao protocolo #{protocolo_h}.")
    return {
        "assunto": "Retirada de equipamento - Protocolo {protocolo}",
        "texto_html": texto,
        "regras_html": ("Deixe o roteador e a fonte separados. Caso você tenha rotina corrida, os aparelhos podem ser "
                        "deixados na portaria do prédio ou com algum vizinho/parente avisado."),
        "texto_whats": WHATS_PADRAO,
    }


def conteudo_padrao_2(protocolo_h):
    return {
        "assunto": "Aviso de retirada de equipamento - Protocolo {protocolo}",
        "texto_html": (f"<b>AVISO DE LOGÍSTICA:</b> nossa equipe técnica estará passando na sua região no "
                       f"<b>período comercial (08:00 às 18:00)</b> para efetuar a retirada do modem/roteador "
                       f"referente ao protocolo #{protocolo_h}."),
        "regras_html": ("• Deixe o roteador junto com a fonte (se perdeu a fonte, nos avise).<br>"
                        "• <b>Apartamentos:</b> pode deixar direto na portaria.<br>"
                        "• Se você mudou de local, use o botão acima para atualizar o endereço no WhatsApp."),
        "texto_whats": "Olá! Recebi o aviso de rota para o protocolo {protocolo}. Quero dar meu 'ok' sobre o endereço cadastrado.",
    }


def aplicar_marcadores(txt, nome, protocolo, endereco):
    return (txt.replace("{nome}", nome)
               .replace("{protocolo}", protocolo)
               .replace("{endereco}", endereco))


def montar_conteudo(modelo, tipo_canc, nome, protocolo, endereco, ctx):
    """Devolve assunto (texto puro), texto/regras (HTML seguro) e texto do WhatsApp."""
    if modelo["tipo"] == "padrao1":
        c = conteudo_padrao_1(tipo_canc, esc(protocolo), ctx)
    elif modelo["tipo"] == "padrao2":
        c = conteudo_padrao_2(esc(protocolo))
    else:  # modelo salvo no banco (texto simples com marcadores)
        corpo = esc(modelo.get("texto", ""))
        corpo = aplicar_marcadores(corpo, esc(nome), esc(protocolo), esc(endereco)).replace("\n", "<br>")
        regras = esc(modelo.get("regras") or REGRAS_PADRAO).replace("\n", "<br>")
        c = {
            "assunto": modelo.get("assunto") or "Retirada de equipamento - Protocolo {protocolo}",
            "texto_html": corpo,
            "regras_html": regras,
            "texto_whats": modelo.get("texto_whats") or WHATS_PADRAO,
        }
    c["assunto"] = aplicar_marcadores(c["assunto"], nome, protocolo, endereco)
    c["texto_whats"] = aplicar_marcadores(c["texto_whats"], nome, protocolo, endereco)
    return c


def preparar_dados(row, modelo, ctx, envio_id):
    nome = pegar(row, "Cliente", "nome", padrao="Cliente")
    protocolo = pegar(row, "BA", "protocolo")
    email = pegar(row, "Email", "email").lower()

    rua = pegar(row, "Endereço", "endereco")
    numero = pegar(row, "Número", "numero")
    bairro = pegar(row, "Bairro")
    cep = pegar(row, "Cep")
    partes = []
    if rua: partes.append(rua)
    if numero: partes.append(f"Nº {numero}")
    if bairro: partes.append(bairro)
    if cep: partes.append(f"CEP: {cep}")
    endereco = " - ".join(partes) if partes else "Endereço incompleto na planilha"

    tipo_bruto = pegar(row, "Tipo", "tipo_cancelamento", padrao="padrao").lower()
    if "involunt" in tipo_bruto:
        tipo_canc = "involuntario"
    elif "volunt" in tipo_bruto:
        tipo_canc = "voluntario"
    else:
        tipo_canc = "padrao"

    c = montar_conteudo(modelo, tipo_canc, nome, protocolo, endereco, ctx)

    # Link do WhatsApp (rastreado pela Edge Function se configurada)
    texto_w = f"{c['texto_whats']} Meu endereço cadastrado é: {endereco}"
    link_wa = f"https://api.whatsapp.com/send?phone={ctx['num_whatsapp']}&text={urllib.parse.quote(texto_w)}"
    if ctx["url_clique"]:
        link = (f"{ctx['url_clique']}?protocolo={urllib.parse.quote(protocolo)}"
                f"&envio={envio_id}&dest={urllib.parse.quote(link_wa)}")
    else:
        link = link_wa

    corpo_html = HTML_TEMPLATE.format(
        empresa=esc(ctx["empresa"]),
        nome=esc(nome),
        texto_dinamico=c["texto_html"],
        endereco_completo_cliente=esc(endereco),
        regras_coleta=c["regras_html"],
        whatsapp_link=esc(link),
        identificacao=esc(ctx["identificacao"]),
    )
    texto_puro = (
        f"Olá, {nome}!\n\n{html_para_texto(c['texto_html'])}\n\n"
        f"Endereço para retirada: {endereco}\n\n"
        f"Confirme o endereço pelo WhatsApp: {link_wa}\n\n"
        f"{html_para_texto(c['regras_html'])}\n\n"
        f"{ctx['empresa']}\n{ctx['identificacao']}\n"
        f"Para não receber mais mensagens, responda com a palavra SAIR."
    )
    return {
        "email": email, "nome": nome, "protocolo": protocolo, "endereco": endereco,
        "assunto": c["assunto"], "html": corpo_html, "texto": texto_puro,
    }


def construir_mensagem(conta, email_destino, dados):
    msg = EmailMessage()
    msg["Subject"] = dados["assunto"]
    msg["From"] = formataddr((conta.get("nome_remetente") or cfg("EMPRESA_NOME"), conta["email"]))
    msg["To"] = email_destino
    msg["Reply-To"] = conta["email"]
    msg["List-Unsubscribe"] = f"<mailto:{conta['email']}?subject=SAIR>"
    msg.set_content(dados["texto"])
    msg.add_alternative(dados["html"], subtype="html")
    return msg


# =============================================================================
# ENVIO (SMTP com conexão reaproveitada) E CONTROLE DE CONTAS
# =============================================================================
class GerenteSMTP:
    def __init__(self):
        self.conexoes = {}

    def fechar_uma(self, email):
        smtp = self.conexoes.pop(email, None)
        if smtp:
            try:
                smtp.quit()
            except Exception:
                pass

    def fechar(self):
        for email in list(self.conexoes):
            self.fechar_uma(email)

    def enviar(self, conta, msg):
        email = conta["email"]
        for tentativa in range(2):
            try:
                smtp = self.conexoes.get(email)
                if smtp is None:
                    smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
                    smtp.login(email, conta["_senha"])
                    self.conexoes[email] = smtp
                smtp.send_message(msg)
                return
            except (smtplib.SMTPServerDisconnected, ConnectionError, OSError):
                self.fechar_uma(email)
                if tentativa == 1:
                    raise


def conta_esgotada(err):
    t = str(err).lower()
    return (isinstance(err, smtplib.SMTPAuthenticationError)
            or "5.4.5" in t or "daily user sending" in t or "sending limit" in t)


def escolher_conta(contas, enviados_hoje, ponteiro):
    n = len(contas)
    for k in range(n):
        c = contas[(ponteiro + k) % n]
        if enviados_hoje.get(c["email"], 0) < int(c.get("limite_diario") or 0):
            return c, (ponteiro + k + 1) % n
    return None, ponteiro


def carregar_contas_ativas(sb):
    res = sb.table("contas_email").select("*").eq("ativa", True).execute()
    contas, sem_senha = [], []
    for c in (res.data or []):
        c["_senha"] = revelar_senha(c.get("senha_app"))
        (contas if c["_senha"] else sem_senha).append(c)
    if sem_senha:
        st.warning("⚠️ Contas ignoradas por senha ilegível (confira a CHAVE_CRIPTO nos secrets): "
                   + ", ".join(c["email"] for c in sem_senha))
    return contas


def contar_enviados_hoje(sb):
    try:
        regs = buscar_todos(sb, "envios_email", "conta", {"status": "enviado"},
                            gte=("data_hora", inicio_do_dia_utc_iso()))
    except Exception:
        return {}
    cont = {}
    for r in regs:
        cont[r["conta"]] = cont.get(r["conta"], 0) + 1
    return cont


def registrar_envio(sb, envio_id, dados, conta_email, modelo_nome, status, erro=""):
    try:
        sb.table("envios_email").insert({
            "envio_id": envio_id, "protocolo": dados["protocolo"], "email": dados["email"],
            "nome": dados["nome"], "conta": conta_email, "modelo": modelo_nome,
            "status": status, "erro": str(erro)[:300], "data_hora": agora_utc_iso(),
        }).execute()
        return True
    except Exception:
        return False


def carregar_modelos_db(sb):
    try:
        res = sb.table("modelos_email").select("*").eq("ativo", True).order("id").execute()
        return res.data or []
    except Exception:
        return []


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


# =============================================================================
# IA (Google Gemini - camada gratuita). A IA só gera RASCUNHOS de modelo.
# =============================================================================
def gerar_modelos_ia(situacao, tom, qtd):
    chave = cfg("GEMINI_API_KEY")
    if not chave:
        raise RuntimeError("Configure GEMINI_API_KEY nos secrets (chave grátis em aistudio.google.com).")
    modelo_ia = cfg("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo_ia}:generateContent"
    prompt = (
        "Você escreve e-mails curtos em português do Brasil para uma empresa de logística que recolhe "
        "equipamentos (modem/roteador) de clientes.\n"
        f"Situação: {situacao}\nTom: {tom}\n"
        f"Escreva {qtd} variações diferentes.\n"
        "Regras obrigatórias:\n"
        "- Use exatamente os marcadores {nome} e {protocolo} (e {endereco} se fizer sentido). "
        "Não use nenhum outro marcador entre chaves.\n"
        "- NÃO invente valores em reais, multas, prazos, datas, horários ou telefones.\n"
        "- NÃO afirme ser a operadora; escreva em nome da empresa de logística.\n"
        "- Texto simples, sem HTML, no máximo 90 palavras, sem ameaças e sem urgência exagerada.\n"
        'Responda SOMENTE com um JSON: uma lista de objetos {"assunto": "...", "texto": "..."}.'
    )
    corpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8},
    }
    r = requests.post(url, headers={"x-goog-api-key": chave, "Content-Type": "application/json"},
                      json=corpo, timeout=60)
    r.raise_for_status()
    bruto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    dados = json.loads(bruto)
    if isinstance(dados, dict):
        dados = dados.get("variacoes") or dados.get("modelos") or [dados]
    return [{"assunto": str(d.get("assunto", "")).strip(), "texto": str(d.get("texto", "")).strip()}
            for d in dados if isinstance(d, dict) and d.get("texto")]


def avisos_do_modelo(assunto, texto):
    """Checagens automáticas para pegar invenções da IA antes de salvar."""
    avisos = []
    conjunto = f"{assunto}\n{texto}"
    for marcador in ("{nome}", "{protocolo}"):
        if marcador not in conjunto:
            avisos.append(f"Não usa o marcador {marcador}.")
    sem_marcadores = re.sub(r"\{\w+\}", "", conjunto)
    if re.search(r"R\$|\d", sem_marcadores):
        avisos.append("Contém número ou valor em R$ — confirme se a informação é verdadeira.")
    desconhecidos = set(re.findall(r"\{(\w+)\}", conjunto)) - {"nome", "protocolo", "endereco"}
    if desconhecidos:
        avisos.append("Marcadores desconhecidos (não serão preenchidos): " + ", ".join(sorted(desconhecidos)))
    if "<" in conjunto and ">" in conjunto:
        avisos.append("Contém HTML — será exibido como texto.")
    return avisos


def formulario_salvar_modelo(sb, chave, assunto_ini="", texto_ini=""):
    nome = st.text_input("Nome do modelo:", key=f"mn_{chave}")
    assunto = st.text_input("Assunto:", value=assunto_ini, key=f"ma_{chave}")
    texto = st.text_area("Texto (use {nome}, {protocolo}, {endereco}):", value=texto_ini, height=160, key=f"mt_{chave}")
    regras = st.text_area("Informações importantes (caixa cinza do e-mail):", value=REGRAS_PADRAO, height=80, key=f"mr_{chave}")
    for aviso in avisos_do_modelo(assunto, texto):
        st.warning("⚠️ " + aviso)
    if st.button("💾 Salvar modelo", key=f"ms_{chave}", type="primary"):
        if not (nome.strip() and assunto.strip() and texto.strip()):
            st.error("Preencha nome, assunto e texto.")
            return
        try:
            sb.table("modelos_email").insert({
                "nome": nome.strip(), "assunto": assunto.strip(), "texto": texto.strip(),
                "regras": regras.strip(), "texto_whats": WHATS_PADRAO, "ativo": True,
            }).execute()
            st.success("✅ Modelo salvo! Ele já aparece na aba de disparos.")
        except Exception as e:
            st.error(f"Erro ao salvar (a tabela modelos_email existe?): {e}")


# =============================================================================
# INTERFACE
# =============================================================================
def _bloco_metricas(sb):
    st.markdown("### 📊 Métricas de Engajamento (Cliques no WhatsApp)")
    col_met1, col_met2 = st.columns([3, 1])
    with col_met2:
        if st.button("🔄 Atualizar Cliques"):
            st.rerun()
    try:
        res_cliques = sb.table("cliques_email").select("*").execute()
        if res_cliques.data:
            df_cliques = pd.DataFrame(res_cliques.data)
            total_cliques = len(df_cliques)
            unicos = df_cliques["envio_id"].nunique() if "envio_id" in df_cliques.columns else total_cliques
            c1, c2 = st.columns(2)
            c1.metric("Total de Cliques Registrados", total_cliques)
            c2.metric("Clientes Únicos que Clicaram", unicos)
            with st.expander("🔍 Ver Detalhes dos Cliques"):
                st.dataframe(df_cliques, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum clique registrado até o momento.")
    except Exception as e:
        st.error(f"Erro ao carregar métricas de clique: {e}")


def _aba_disparo(sb):
    empresa = cfg("EMPRESA_NOME")
    if not empresa:
        st.error("Defina `EMPRESA_NOME` (e `EMPRESA_IDENTIFICACAO`, ex.: CNPJ e contato) nos secrets antes de disparar. "
                 "O destinatário precisa saber quem está enviando.")
        return

    try:
        contas = carregar_contas_ativas(sb)
    except Exception as e:
        st.error(f"Erro ao carregar contas: {e}")
        return
    if not contas:
        st.warning("⚠️ Nenhuma conta de e-mail ativa. Cadastre e ative uma na aba 'Contas Remetentes'.")
        return

    enviados_hoje = contar_enviados_hoje(sb)
    capacidade = sum(max(0, int(c.get("limite_diario") or 0) - enviados_hoje.get(c["email"], 0)) for c in contas)
    st.info(f"✅ {len(contas)} conta(s) ativa(s) · capacidade restante hoje: **{capacidade}** envios")

    arquivo = st.file_uploader("📂 Faça upload da planilha (.xlsx, .xls, .csv ou .txt)",
                               type=["xlsx", "xls", "csv", "txt"])
    if not arquivo:
        return

    try:
        df = carregar_dataframe_inteligente(arquivo)
        df = df.dropna(how='all').reset_index(drop=True)
        df.columns = [str(col).strip() for col in df.columns]
        st.success(f"📋 Planilha carregada: **{len(df)} registros**.")
        with st.expander("👁️ Ver prévia da planilha"):
            st.dataframe(df.head(5), use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        return

    st.markdown("---")
    st.markdown("### Configurações da Campanha")

    modelos_db = carregar_modelos_db(sb)
    opcoes = {
        "[Padrão 1] Cancelamento (voluntário/involuntário)": {"tipo": "padrao1"},
        "[Padrão 2] Comunicado de rota técnica": {"tipo": "padrao2"},
    }
    for m in modelos_db:
        opcoes[f"[Salvo] {m['nome']}"] = {"tipo": "db", **m}

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        nome_modelo = st.selectbox("Modelo do e-mail:", list(opcoes.keys()))
        num_whatsapp = st.text_input("WhatsApp de destino (com DDI+DDD):", value=str(cfg("WHATSAPP_NUMERO")))
    with col_m2:
        delay_min = st.number_input("Intervalo mínimo entre envios (s):", min_value=1, max_value=60, value=4)
        delay_max = st.number_input("Intervalo máximo entre envios (s):", min_value=1, max_value=60, value=8)
        permitir_reenvio = st.checkbox("Permitir reenviar para quem já recebeu", value=False)

    if not num_whatsapp.strip():
        st.warning("Informe o WhatsApp de destino (ou defina `WHATSAPP_NUMERO` nos secrets).")
        return
    if not cfg("URL_FUNCAO_CLIQUE"):
        st.caption("ℹ️ `URL_FUNCAO_CLIQUE` não definida nos secrets: o botão abrirá o WhatsApp direto, sem contar cliques.")

    modelo = opcoes[nome_modelo]
    ctx = {
        "empresa": empresa,
        "identificacao": str(cfg("EMPRESA_IDENTIFICACAO")),
        "valor_multa": str(cfg("VALOR_MULTA")),
        "url_clique": str(cfg("URL_FUNCAO_CLIQUE")),
        "num_whatsapp": re.sub(r"\D", "", num_whatsapp),
    }

    # ---- Prévia e teste ----
    primeira = df.iloc[0]
    dados_previa = preparar_dados(primeira, modelo, ctx, "previa")
    with st.expander("👁️ Pré-visualizar o e-mail (1ª linha da planilha)"):
        st.caption(f"Assunto: {dados_previa['assunto']}")
        components.html(dados_previa["html"], height=720, scrolling=True)

    col_t1, col_t2 = st.columns([3, 1])
    email_teste = col_t1.text_input("E-mail para teste:", placeholder="seu@email.com").strip().lower()
    if col_t2.button("📨 Enviar teste", use_container_width=True):
        if not email_valido(email_teste):
            st.error("Informe um e-mail de teste válido.")
        else:
            gerente_t = GerenteSMTP()
            try:
                gerente_t.enviar(contas[0], construir_mensagem(contas[0], email_teste, dados_previa))
                st.success(f"✅ Teste enviado para {email_teste} via {contas[0]['email']}. Confira também a caixa de spam.")
            except Exception as e:
                st.error(f"Falha no teste: {e}")
            finally:
                gerente_t.fechar()

    st.markdown("---")
    revisado = st.checkbox("✅ Revisei a prévia e recebi o e-mail de teste")

    if "parar_disparo" not in st.session_state:
        st.session_state["parar_disparo"] = False
    col_btn_start, col_btn_stop = st.columns([3, 1])
    with col_btn_stop:
        if st.button("🛑 PARAR", type="secondary", use_container_width=True):
            st.session_state["parar_disparo"] = True
    iniciar = col_btn_start.button("🚀 Iniciar Disparos em Massa", type="primary",
                                   use_container_width=True, disabled=not revisado)
    if not iniciar:
        return

    # ---- Disparo ----
    st.session_state["parar_disparo"] = False
    if delay_max < delay_min:
        delay_min, delay_max = delay_max, delay_min

    try:
        descadastrados = {r["email"].lower() for r in buscar_todos(sb, "descadastros", "email", ordem="email")}
        ja_enviados = {f"{r['protocolo']}|{r['email']}" for r in
                       buscar_todos(sb, "envios_email", "protocolo,email", {"status": "enviado"})}
    except Exception as e:
        st.error(f"Não foi possível consultar descadastros/histórico (rodou o SQL de migração?): {e}")
        return

    total = len(df)
    barra = st.progress(0)
    status_txt = st.empty()
    resultado = {}
    sucessos = erros = ignorados = falhas_log = erros_seguidos = 0
    vistos = set()
    ponteiro = 0
    gerente = GerenteSMTP()

    try:
        for pos, (_, row) in enumerate(df.iterrows()):
            if st.session_state.get("parar_disparo"):
                st.warning(f"⚠️ Disparo interrompido no registro {pos}/{total}.")
                break

            envio_id = str(uuid.uuid4())
            dados = preparar_dados(row, modelo, ctx, envio_id)
            chave = f"{dados['protocolo']}|{dados['email']}"
            motivo = None
            if not email_valido(dados["email"]):
                motivo = "IGNORADO: e-mail inválido/fictício"
            elif dados["email"] in descadastrados:
                motivo = "IGNORADO: cliente pediu para sair (descadastrado)"
            elif chave in vistos:
                motivo = "IGNORADO: duplicado na planilha"
            elif not permitir_reenvio and chave in ja_enviados:
                motivo = "IGNORADO: já enviado anteriormente"
            if motivo:
                ignorados += 1
                resultado[pos] = (motivo, agora_br().strftime('%d/%m/%Y %H:%M:%S'))
                barra.progress((pos + 1) / total)
                continue
            vistos.add(chave)

            conta, ponteiro = escolher_conta(contas, enviados_hoje, ponteiro)
            if conta is None:
                st.warning("⛔ Limite diário atingido em todas as contas. Continue amanhã com a mesma planilha "
                           "(quem já recebeu será pulado automaticamente).")
                break

            status_txt.text(f"Enviando {pos + 1}/{total} para {dados['email']} via [{conta['email']}]...")
            hora = agora_br().strftime('%d/%m/%Y %H:%M:%S')
            try:
                gerente.enviar(conta, construir_mensagem(conta, dados["email"], dados))
                sucessos += 1
                erros_seguidos = 0
                enviados_hoje[conta["email"]] = enviados_hoje.get(conta["email"], 0) + 1
                ja_enviados.add(chave)
                resultado[pos] = (f"Sucesso (via {conta['email']})", hora)
                if not registrar_envio(sb, envio_id, dados, conta["email"], nome_modelo, "enviado"):
                    falhas_log += 1
            except Exception as err:
                erros += 1
                erros_seguidos += 1
                resultado[pos] = (f"Erro: {err}", hora)
                if not registrar_envio(sb, envio_id, dados, conta["email"], nome_modelo, "erro", err):
                    falhas_log += 1
                if conta_esgotada(err):
                    enviados_hoje[conta["email"]] = 10 ** 9
                    gerente.fechar_uma(conta["email"])
                    st.warning(f"Conta {conta['email']} bloqueada/limite atingido — removida desta campanha.")
                if erros_seguidos >= MAX_ERROS_SEGUIDOS:
                    st.error(f"🛑 {MAX_ERROS_SEGUIDOS} erros seguidos: campanha abortada para proteger as contas.")
                    break

            barra.progress((pos + 1) / total)
            time.sleep(random.uniform(delay_min, delay_max))
    finally:
        gerente.fechar()

    st.success(f"🎉 Processo encerrado! Sucessos: {sucessos} | Ignorados: {ignorados} | Erros: {erros}")
    if falhas_log:
        st.warning(f"⚠️ {falhas_log} envio(s) não foram gravados no histórico (tabela envios_email). "
                   "Esses clientes podem receber de novo numa próxima rodada.")

    df['status_envio'] = [resultado.get(i, ("NÃO PROCESSADO", ""))[0] for i in range(total)]
    df['data_hora'] = [resultado.get(i, ("", ""))[1] for i in range(total)]
    buffer_rel = BytesIO()
    with pd.ExcelWriter(buffer_rel, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Resultado')
    buffer_rel.seek(0)
    st.download_button(
        label="📊 Baixar Relatório do Disparo (.xlsx)",
        data=buffer_rel,
        file_name=f"relatorio_disparos_{agora_br().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def _aba_modelos_ia(sb):
    st.markdown("### 🤖 Gerar modelos de e-mail com IA")
    st.caption("A IA só cria **rascunhos**. Você revisa, edita e salva; o disparo usa apenas modelos salvos por você.")

    if not cfg("GEMINI_API_KEY"):
        st.info("Para usar a IA, crie uma chave grátis em aistudio.google.com e coloque `GEMINI_API_KEY` nos secrets. "
                "Enquanto isso, você pode escrever modelos manualmente abaixo.")
    else:
        with st.form("form_ia"):
            situacao = st.text_area("Descreva a situação:", height=90,
                                    placeholder="Ex.: cliente cancelou o plano e precisa devolver o modem; peça para confirmar o endereço pelo WhatsApp.")
            col1, col2 = st.columns(2)
            tom = col1.selectbox("Tom:", ["Educado e objetivo", "Amigável", "Formal", "Firme, porém respeitoso"])
            qtd = col2.number_input("Quantidade de variações:", min_value=1, max_value=5, value=3)
            gerar = st.form_submit_button("✨ Gerar rascunhos", type="primary")
        if gerar:
            if not situacao.strip():
                st.warning("Descreva a situação.")
            else:
                try:
                    with st.spinner("Gerando..."):
                        st.session_state["ia_resultados"] = gerar_modelos_ia(situacao.strip(), tom, int(qtd))
                    st.session_state["ia_lote"] = st.session_state.get("ia_lote", 0) + 1
                except Exception as e:
                    st.error(f"Erro ao gerar com a IA: {e}")

    for i, item in enumerate(st.session_state.get("ia_resultados", [])):
        with st.expander(f"Rascunho {i + 1}: {item['assunto'][:60]}", expanded=(i == 0)):
            formulario_salvar_modelo(sb, f"ia_{st.session_state.get('ia_lote', 0)}_{i}", item["assunto"], item["texto"])

    with st.expander("✍️ Escrever modelo manualmente"):
        formulario_salvar_modelo(sb, "manual")

    st.markdown("---")
    st.markdown("### Modelos salvos")
    try:
        res = sb.table("modelos_email").select("*").order("id").execute()
        if not res.data:
            st.info("Nenhum modelo salvo ainda.")
        for m in (res.data or []):
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.write(f"{'🟢' if m['ativo'] else '🔴'} **{m['nome']}** — {m['assunto']}")
            if c2.button("Ativar/Desativar", key=f"mtog_{m['id']}"):
                sb.table("modelos_email").update({"ativo": not m["ativo"]}).eq("id", m["id"]).execute()
                st.rerun()
            if c3.button("Excluir", key=f"mdel_{m['id']}"):
                sb.table("modelos_email").delete().eq("id", m["id"]).execute()
                st.rerun()
    except Exception as e:
        st.error(f"Erro ao listar modelos (a tabela modelos_email existe?): {e}")


def _aba_contas(sb):
    st.markdown("### Cadastrar Nova Conta de E-mail")
    if not _fernet():
        st.warning("🔐 `CHAVE_CRIPTO` não configurada: as senhas de app seriam salvas em texto puro. Gere uma chave com "
                   "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
                   "e coloque nos secrets (e `cryptography` no requirements.txt).")
    st.caption("Use sempre **senha de app** do Google, nunca a senha normal da conta. Contas novas: comece com limite baixo (30–50/dia).")

    with st.form("form_nova_conta", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            novo_email = st.text_input("E-mail Remetente (ex: conta@gmail.com)").strip().lower()
            nome_rem = st.text_input("Nome de Exibição", value=str(cfg("EMPRESA_NOME"))).strip()
        with col_b:
            nova_senha = st.text_input("Senha de App", type="password").strip()
            limite_d = st.number_input("Limite Diário de Envios", min_value=10, max_value=LIMITE_MAXIMO_POR_CONTA, value=50)
        if st.form_submit_button("➕ Salvar Conta", type="primary"):
            if novo_email and nova_senha:
                try:
                    sb.table("contas_email").insert({
                        "email": novo_email, "senha_app": proteger_senha(nova_senha),
                        "nome_remetente": nome_rem, "limite_diario": int(limite_d), "ativa": True,
                    }).execute()
                    st.success(f"✅ Conta {novo_email} cadastrada!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar conta: {e}")
            else:
                st.warning("Preencha e-mail e senha de app.")

    st.markdown("---")
    st.markdown("### Contas Cadastradas")
    try:
        dados_contas = sb.table("contas_email").select("*").order("id").execute().data
        if not dados_contas:
            st.info("Nenhuma conta registrada ainda.")
            return
        usados = contar_enviados_hoje(sb)
        legadas = [r for r in dados_contas if r.get("senha_app") and not str(r["senha_app"]).startswith(PREFIXO_CRIPTO)]
        if legadas and _fernet():
            st.warning(f"{len(legadas)} conta(s) ainda com senha em texto puro no banco.")
            if st.button("🔐 Proteger senhas existentes agora"):
                for r in legadas:
                    sb.table("contas_email").update({"senha_app": proteger_senha(r["senha_app"])}).eq("id", r["id"]).execute()
                st.success("Senhas criptografadas.")
                st.rerun()
        for r in dados_contas:
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            c1.write(f"📧 **{r['email']}** ({r['nome_remetente']})")
            c2.write(f"Hoje: {usados.get(r['email'], 0)}/{r['limite_diario']}")
            c3.write("🟢 Ativa" if r['ativa'] else "🔴 Inativa")
            if c4.button("Desativar" if r['ativa'] else "Ativar", key=f"tog_{r['id']}"):
                sb.table("contas_email").update({"ativa": not r['ativa']}).eq("id", r['id']).execute()
                st.rerun()
    except Exception as e:
        st.error(f"Erro ao listar contas: {e}")


def _aba_descadastros(sb):
    st.markdown("### 🚫 Lista de quem pediu para não receber")
    st.caption("Quem responder **SAIR** deve ser cadastrado aqui. Esses e-mails são pulados automaticamente em todos os disparos.")
    texto = st.text_area("Cole os e-mails (um por linha):", height=100, key="desc_txt")
    if st.button("➕ Adicionar à lista", type="primary"):
        emails = {e.strip().lower() for e in re.split(r"[\s,;]+", texto) if e.strip()}
        validos = [e for e in emails if email_valido(e)]
        if not validos:
            st.warning("Nenhum e-mail válido encontrado.")
        else:
            try:
                sb.table("descadastros").upsert(
                    [{"email": e, "motivo": "pediu para sair", "data_hora": agora_utc_iso()} for e in validos],
                    on_conflict="email").execute()
                st.success(f"✅ {len(validos)} e-mail(s) adicionados.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar (a tabela descadastros existe?): {e}")
    try:
        lista = buscar_todos(sb, "descadastros", "*", ordem="email")
        st.write(f"Total na lista: **{len(lista)}**")
        for r in lista[:200]:
            c1, c2 = st.columns([4, 1])
            c1.write(r["email"])
            if c2.button("Remover", key=f"rmdesc_{r['email']}"):
                sb.table("descadastros").delete().eq("email", r["email"]).execute()
                st.rerun()
    except Exception as e:
        st.error(f"Erro ao listar: {e}")


def _aba_historico(sb):
    st.markdown("### 📜 Histórico de envios")
    try:
        dados = sb.table("envios_email").select("*").order("data_hora", desc=True).limit(1000).execute().data
    except Exception as e:
        st.error(f"Erro ao carregar histórico (a tabela envios_email existe?): {e}")
        return
    if not dados:
        st.info("Nenhum envio registrado ainda.")
        return
    df = pd.DataFrame(dados)
    df["Horário"] = pd.to_datetime(df["data_hora"], utc=True).dt.tz_convert("America/Sao_Paulo").dt.strftime("%d/%m/%Y %H:%M:%S")
    c1, c2 = st.columns(2)
    filtro_status = c1.selectbox("Status:", ["Todos", "enviado", "erro"])
    busca = c2.text_input("Buscar protocolo ou e-mail:").strip()
    if filtro_status != "Todos":
        df = df[df["status"] == filtro_status]
    if busca:
        mask = (df["protocolo"].astype(str).str.contains(busca, case=False, na=False, regex=False)
                | df["email"].astype(str).str.contains(busca, case=False, na=False, regex=False))
        df = df[mask]
    m1, m2 = st.columns(2)
    m1.metric("Enviados (listados)", int((df["status"] == "enviado").sum()))
    m2.metric("Erros (listados)", int((df["status"] == "erro").sum()))
    vitrine = df[["Horário", "nome", "email", "protocolo", "conta", "modelo", "status", "erro"]]
    st.dataframe(vitrine, use_container_width=True, hide_index=True)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        vitrine.to_excel(w, index=False, sheet_name="Historico")
    buf.seek(0)
    st.download_button("📊 Baixar histórico (.xlsx)", data=buf, file_name="historico_envios.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)


def renderizar_aba_disparador_emails(supabase_client):
    st.subheader("📧 Disparador de E-mails")
    _bloco_metricas(supabase_client)
    st.markdown("---")

    t_disp, t_ia, t_contas, t_desc, t_hist = st.tabs(
        ["🚀 Disparos", "🤖 Modelos (IA)", "🔑 Contas Remetentes", "🚫 Descadastros", "📜 Histórico"]
    )
    with t_disp:
        _aba_disparo(supabase_client)
    with t_ia:
        _aba_modelos_ia(supabase_client)
    with t_contas:
        _aba_contas(supabase_client)
    with t_desc:
        _aba_descadastros(supabase_client)
    with t_hist:
        _aba_historico(supabase_client)
