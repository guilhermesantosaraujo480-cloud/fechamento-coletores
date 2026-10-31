"""Leitura de comprovantes de vale (Pix/transferência) feita por IA: o que pedir e como CONFERIR o que ela devolveu.

A IA só sugere (valor, data, nome de quem recebeu, código da transação). Quem lança o vale é o administrador, depois de conferir.
Sem Streamlit e sem rede: tudo aqui é testável.
"""
import re
from datetime import date, datetime, timedelta

LIMITE_VALOR = 100_000.0     # acima disso a leitura é tratada como erro
DIAS_ANTIGO = 400            # comprovante mais velho que isso gera aviso

PROMPT = (
    "Você lê comprovantes de pagamento brasileiros (Pix, TED, transferência, depósito) a partir de uma foto ou captura de tela. "
    "Devolva SOMENTE um JSON com estes campos: "
    '{"tipo": "pix|ted|transferencia|deposito|outro|nao_e_comprovante", "legivel": true|false, '
    '"valor": número em reais com ponto decimal (ex.: 150.5) ou null, "data": "AAAA-MM-DD" ou null, "hora": "HH:MM" ou null, '
    '"beneficiario": "nome de quem RECEBEU o dinheiro" ou null, "pagador": "nome de quem PAGOU" ou null, '
    '"id_transacao": "código da transação/ID/autenticação, exatamente como aparece" ou null, "banco": texto ou null}. '
    "Regras: não invente nada; se um campo não estiver visível, use null. O valor é o valor da transferência (não saldo, não tarifa). "
    "Se a imagem não for um comprovante de pagamento, use tipo nao_e_comprovante e legivel false."
)


def _numero(valor):
    """150, 150.5, '150,50', 'R$ 1.234,56' -> float (None se não der)."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    t = re.sub(r"[^\d,.\-]", "", str(valor or ""))
    if not t:
        return None
    if "," in t:  # formato brasileiro: ponto separa milhar, vírgula separa centavos
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", t):  # '1.234.567' ou '1.500' (milhar, sem centavos)
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def _data(valor):
    t = str(valor or "").strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, formato).date()
        except ValueError:
            continue
    return None


def normalizar_id(texto):
    """Código da transação comparável (maiúsculas, só letras/números). Curto demais (< 8) vira None: causaria 'duplicado' falso."""
    t = re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())
    return t if len(t) >= 8 else None


def interpretar(bruto, hoje=None):
    """Confere o JSON da IA. Devolve dict: valor, data, nome, pagador, id_transacao, tipo, legivel, avisos (lista de textos)."""
    hoje = hoje or date.today()
    bruto = bruto if isinstance(bruto, dict) else {}
    avisos = []
    tipo = str(bruto.get("tipo") or "outro").strip().lower()
    legivel = bool(bruto.get("legivel", True)) and tipo != "nao_e_comprovante"
    if not legivel:
        avisos.append("A IA não reconheceu um comprovante legível nessa foto. Preencha à mão.")
    valor = _numero(bruto.get("valor"))
    if valor is None or valor <= 0:
        valor = None
        avisos.append("Não consegui ler o valor: digite à mão.")
    elif valor > LIMITE_VALOR:
        avisos.append(f"Valor lido muito alto (R$ {valor:,.2f}): confira com a foto.")
    data = _data(bruto.get("data"))
    if data is None:
        avisos.append("Não consegui ler a data: confira a data do lançamento.")
    elif data > hoje + timedelta(days=1):
        avisos.append("A data lida está no futuro: confira.")
        data = None
    elif (hoje - data).days > DIAS_ANTIGO:
        avisos.append("A data lida é bem antiga: confira.")
    return {
        "valor": valor, "data": data, "tipo": tipo, "legivel": legivel,
        "nome": str(bruto.get("beneficiario") or "").strip(), "pagador": str(bruto.get("pagador") or "").strip(),
        "id_transacao": normalizar_id(bruto.get("id_transacao")), "banco": str(bruto.get("banco") or "").strip(), "avisos": avisos,
    }
