"""Montagem do e-mail: modelos padrão, modelos salvos, HTML e versão em texto puro."""
import urllib.parse
from email.message import EmailMessage
from email.utils import formataddr

from core.utils import escapar as esc

from .colunas import montar_endereco, tipo_cancelamento
from .utils import html_para_texto

REGRAS_PADRAO = "Deixe o roteador e a fonte separados. Se preferir, pode deixar na portaria do prédio."
WHATS_PADRAO = "Olá! Vim pelo e-mail do protocolo {protocolo}. Quero confirmar meu endereço para a coleta."
ASSUNTO_PADRAO = "Retirada de equipamento - Protocolo {protocolo}"
MARCADORES = ("nome", "protocolo", "endereco")

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


def conteudo_padrao_1(tipo, protocolo_h, valor_multa):
    if tipo == "voluntario":
        texto = (f"Como você solicitou o desligamento do seu plano, precisamos prosseguir com a etapa final do processo: "
                 f"a devolução dos equipamentos que estão sob sua responsabilidade. "
                 f"O recolhimento está associado ao protocolo #{protocolo_h}.")
    elif tipo == "involuntario":
        trecho = (f"multas contratuais adicionais de até <b>{esc(valor_multa)} por equipamento</b> retido"
                  if valor_multa else "cobranças adicionais por equipamento retido")
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


def aplicar_marcadores(texto, nome, protocolo, endereco):
    return (texto.replace("{nome}", nome).replace("{protocolo}", protocolo).replace("{endereco}", endereco))


def montar_conteudo(modelo, tipo_canc, nome, protocolo, endereco, valor_multa=""):
    """Assunto em texto puro; texto/regras em HTML já escapado; texto do WhatsApp em texto puro."""
    if modelo["tipo"] == "padrao1":
        c = conteudo_padrao_1(tipo_canc, esc(protocolo), valor_multa)
    elif modelo["tipo"] == "padrao2":
        c = conteudo_padrao_2(esc(protocolo))
    else:  # modelo salvo no banco (texto simples com marcadores)
        corpo = aplicar_marcadores(esc(modelo.get("texto", "")), esc(nome), esc(protocolo), esc(endereco))
        c = {
            "assunto": modelo.get("assunto") or ASSUNTO_PADRAO,
            "texto_html": corpo.replace("\n", "<br>"),
            "regras_html": esc(modelo.get("regras") or REGRAS_PADRAO).replace("\n", "<br>"),
            "texto_whats": modelo.get("texto_whats") or WHATS_PADRAO,
        }
    c["assunto"] = aplicar_marcadores(c["assunto"], nome, protocolo, endereco)
    c["texto_whats"] = aplicar_marcadores(c["texto_whats"], nome, protocolo, endereco)
    return c


def preparar_dados(reg, modelo, ctx, envio_id):
    """reg: dicionário vindo de colunas.registro_da_linha. ctx: empresa, identificacao, valor_multa, url_clique, num_whatsapp."""
    nome = reg.get("nome") or "Cliente"
    protocolo, email = reg.get("protocolo", ""), reg.get("email", "")
    endereco = montar_endereco(reg)
    c = montar_conteudo(modelo, tipo_cancelamento(reg), nome, protocolo, endereco, ctx.get("valor_multa", ""))

    texto_w = f"{c['texto_whats']} Meu endereço cadastrado é: {endereco}"
    link_wa = f"https://api.whatsapp.com/send?phone={ctx['num_whatsapp']}&text={urllib.parse.quote(texto_w)}"
    if ctx.get("url_clique"):
        link = (f"{ctx['url_clique']}?protocolo={urllib.parse.quote(protocolo)}"
                f"&envio={envio_id}&dest={urllib.parse.quote(link_wa)}")
    else:
        link = link_wa

    corpo_html = HTML_TEMPLATE.format(
        empresa=esc(ctx["empresa"]), nome=esc(nome), texto_dinamico=c["texto_html"],
        endereco_completo_cliente=esc(endereco), regras_coleta=c["regras_html"],
        whatsapp_link=esc(link), identificacao=esc(ctx.get("identificacao", "")),
    )
    texto_puro = (
        f"Olá, {nome}!\n\n{html_para_texto(c['texto_html'])}\n\n"
        f"Endereço para retirada: {endereco}\n\n"
        f"Confirme o endereço pelo WhatsApp: {link_wa}\n\n"
        f"{html_para_texto(c['regras_html'])}\n\n"
        f"{ctx['empresa']}\n{ctx.get('identificacao', '')}\n"
        f"Para não receber mais mensagens, responda com a palavra SAIR."
    )
    return {"email": email, "nome": nome, "protocolo": protocolo, "endereco": endereco,
            "assunto": c["assunto"], "html": corpo_html, "texto": texto_puro}


def construir_mensagem(conta, email_destino, dados, empresa=""):
    msg = EmailMessage()
    msg["Subject"] = dados["assunto"]
    msg["From"] = formataddr((conta.get("nome_remetente") or empresa, conta["email"]))
    msg["To"] = email_destino
    msg["Reply-To"] = conta["email"]
    msg["List-Unsubscribe"] = f"<mailto:{conta['email']}?subject=SAIR>"
    msg.set_content(dados["texto"])
    msg.add_alternative(dados["html"], subtype="html")
    return msg
