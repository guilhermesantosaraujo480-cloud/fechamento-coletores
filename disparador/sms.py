"""SMS (regras puras, sem Streamlit e sem banco): telefone, texto, contagem de partes, variações e triagem.

O SMS sai de um celular Android com o app "SMS Gateway for Android" (ver `sms_gateway.py`). Aqui ficam as regras:
- só celular brasileiro recebe (telefone fixo não recebe SMS);
- acentos (ã, é, ç...) fazem o SMS virar "unicode" e caber só 70 caracteres por parte (em vez de 160): por padrão tiramos os acentos;
- todo SMS leva a frase de saída ("Responda SAIR...") e quem pediu para sair nunca recebe de novo.
"""
import re
import unicodedata
import urllib.parse

from rotas.processamento import numero_do_celular, primeiro_nome

from . import variacoes

AVISO_SAIR = "Responda SAIR p/ nao receber."
MAX_PARTES_ALERTA = 2

# Modelos prontos: curtos, sem ameaça e sem prazo inventado. {nome} = primeiro nome; {link} = conversa no WhatsApp.
MODELOS_PADRAO = [
    {"nome": "Combinar retirada", "texto": "{empresa}: {nome}, vamos combinar a retirada do equipamento (protocolo {protocolo})? "
                                           "Fale com a gente: {link} {sair}"},
    {"nome": "Confirmar endereço", "texto": "{nome}, aqui e da {empresa}. Podemos confirmar seu endereco para retirar o "
                                           "equipamento do protocolo {protocolo}? {link} {sair}"},
    {"nome": "Aviso de rota", "texto": "{empresa}: nossa equipe estara na sua regiao em breve para retirar o equipamento "
                                       "(protocolo {protocolo}). Confirme aqui: {link} {sair}"},
    {"nome": "Pendência", "texto": "{nome}, consta uma devolucao de equipamento pendente (protocolo {protocolo}). "
                                  "Agende a retirada: {link} {sair}"},
    {"nome": "Último lembrete", "texto": "{empresa}: ainda nao conseguimos retirar o equipamento do protocolo {protocolo}. "
                                          "Responda pelo WhatsApp e agendamos: {link} {sair}"},
]

# Alfabeto básico do SMS (GSM 7-bit) e extensões (contam 2). Fora disso o SMS vira unicode (70 por parte).
_GSM = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
_GSM_EXT = set("^{}\\[~]|€")


def tirar_acentos(texto):
    sem = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sem if not unicodedata.combining(c)).replace("ª", "a").replace("º", "o")


def telefone_e164(valor):
    """'+55DDDNUMERO' para celular brasileiro válido; '' caso contrário (fixo e lixo não recebem SMS)."""
    n = numero_do_celular(valor)
    return f"+{n}" if n else ""


def melhor_telefone(*valores):
    """Primeiro celular válido entre vários campos (telefone, telefone2...)."""
    return next((t for t in (telefone_e164(v) for v in valores) if t), "")


def partes(texto):
    """(caracteres, partes, codificação). Parte única: 160 (GSM) ou 70 (unicode); em várias partes: 153 ou 67 cada."""
    texto = str(texto or "")
    if all(c in _GSM or c in _GSM_EXT for c in texto):
        n = sum(2 if c in _GSM_EXT else 1 for c in texto)
        total = 1 if n <= 160 else -(-n // 153)
        return n, max(total, 1) if n else 0, "GSM"
    n = len(texto)
    total = 1 if n <= 70 else -(-n // 67)
    return n, max(total, 1) if n else 0, "Unicode"


def link_conversa(num_whatsapp, protocolo=""):
    """Link curto da conversa com a empresa (cabe em SMS). O cliente toca e o WhatsApp abre com o protocolo escrito."""
    numero = re.sub(r"\D", "", str(num_whatsapp or ""))
    if not numero:
        return ""
    base = f"https://wa.me/{numero}"
    return base + ("?text=" + urllib.parse.quote(f"Protocolo {protocolo}") if protocolo else "")


def montar_texto(modelo, reg, ctx, sem_acentos=True):
    """Texto final de UM destinatário. Garante a frase de saída e tira acentos (opcional)."""
    nome = primeiro_nome(reg.get("nome")) or "Cliente"
    protocolo = str(reg.get("protocolo", "") or "")
    link = ctx.get("link") or link_conversa(ctx.get("num_whatsapp"), protocolo)
    texto = str(modelo)
    tem_sair = "{sair}" in texto or "SAIR" in texto.upper()
    for chave, valor in (("{nome}", nome), ("{protocolo}", protocolo), ("{empresa}", str(ctx.get("empresa", "") or "")),
                         ("{link}", link), ("{sair}", AVISO_SAIR)):
        texto = texto.replace(chave, valor)
    if not tem_sair:
        texto = f"{texto} {AVISO_SAIR}"
    texto = re.sub(r"[ \t]{2,}", " ", texto).strip()
    return tirar_acentos(texto) if sem_acentos else texto


def avisos_do_texto(texto):
    """Alertas para o administrador antes de enviar."""
    n, p, cod = partes(texto)
    avisos = []
    if cod == "Unicode":
        avisos.append("Há acentos/símbolos: o SMS cabe só 70 caracteres por parte (marque “Tirar acentos”).")
    if p > MAX_PARTES_ALERTA:
        avisos.append(f"O texto tem {n} caracteres ({p} partes): vira vários SMS e aumenta o risco de bloqueio. Encurte.")
    if "{" in texto and "}" in texto:
        avisos.append("Sobrou algum campo entre chaves sem preencher (confira os nomes: {nome}, {protocolo}, {empresa}, {link}).")
    if re.search(r"bit\.ly|tinyurl|goo\.gl", texto, re.I):
        avisos.append("Link encurtado costuma ser barrado pelas operadoras: prefira o link do WhatsApp direto.")
    if texto.upper() == texto and len(texto) > 20:
        avisos.append("Texto todo em MAIÚSCULAS parece spam.")
    return avisos


# ------------------------------------------------------------------------------ triagem
def normalizar_bloqueio(valor):
    """Chave de comparação do telefone (só dígitos, com 55)."""
    return numero_do_celular(valor) or re.sub(r"\D", "", str(valor or ""))


def triar(telefone, bloqueados, ja_enviados, permitir_reenvio=False, protocolo="", email="", emails_descadastrados=()):
    """'' se pode enviar; senão o motivo de pular. bloqueados/ja_enviados: conjuntos."""
    if not telefone:
        return "Sem celular válido"
    chave = normalizar_bloqueio(telefone)
    if chave in bloqueados:
        return "Pediu para sair (SMS)"
    if email and str(email).lower() in emails_descadastrados:
        return "Pediu para sair (e-mail)"
    if not permitir_reenvio and f"{protocolo}|{chave}" in ja_enviados:
        return "Já recebeu SMS deste protocolo"
    return ""


def atribuir_textos(total, textos, semente=None):
    """Índice do texto de cada destinatário (balanceado e embaralhado, como nos e-mails)."""
    return variacoes.atribuir(total, [{"peso": 1.0} for _ in textos], semente)


def limitar_janela(agora, ini, fim):
    """True se `agora` (datetime) está dentro da janela de horas [ini, fim). Sem janela = sempre."""
    if ini is None or fim is None:
        return True
    h = agora.hour + agora.minute / 60
    return ini <= h < fim if ini < fim else (h >= ini or h < fim)
