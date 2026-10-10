"""IA gratuita (Google Gemini): só gera RASCUNHOS de modelo. O disparo usa apenas modelos que você aprovou."""
import json
import re

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
MODELO_PADRAO = "gemini-2.0-flash"


class ErroIA(RuntimeError):
    """Mensagem já pronta para mostrar ao usuário."""


def _cabecalho(chave):
    return {"x-goog-api-key": chave, "Content-Type": "application/json"}


def _traduzir_http(resposta):
    codigo = resposta.status_code
    if codigo in (400, 403):
        return "Chave da IA recusada. Confira a GEMINI_API_KEY (se ela vazou, crie outra no AI Studio)."
    if codigo == 404:
        return "Modelo não encontrado. Use o botão 'Ver modelos disponíveis' e copie um nome para GEMINI_MODEL."
    if codigo == 429:
        return "Limite gratuito da IA atingido. Espere alguns minutos (ou até amanhã) e tente de novo."
    return f"A IA respondeu com erro {codigo}."


def listar_modelos_gemini(chave, http=requests):
    """Nomes de modelos que aceitam gerar texto com a sua chave."""
    if not chave:
        raise ErroIA("Configure GEMINI_API_KEY nos secrets.")
    r = http.get(f"{BASE}/models", headers=_cabecalho(chave), params={"pageSize": 100}, timeout=30)
    if r.status_code != 200:
        raise ErroIA(_traduzir_http(r))
    nomes = [m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    return sorted(nomes)


def _extrair_json(texto):
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.I)
    return json.loads(texto)


def montar_prompt(situacao, tom, qtd):
    return (
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


def gerar_modelos_ia(chave, modelo, situacao, tom, qtd, http=requests):
    if not chave:
        raise ErroIA("Configure GEMINI_API_KEY nos secrets (chave grátis em aistudio.google.com).")
    corpo = {
        "contents": [{"parts": [{"text": montar_prompt(situacao, tom, qtd)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8},
    }
    try:
        r = http.post(f"{BASE}/models/{modelo or MODELO_PADRAO}:generateContent",
                      headers=_cabecalho(chave), json=corpo, timeout=60)
    except requests.RequestException as erro:
        raise ErroIA(f"Não foi possível falar com a IA: {erro}") from erro
    if r.status_code != 200:
        raise ErroIA(_traduzir_http(r))
    try:
        dados = _extrair_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, ValueError) as erro:
        raise ErroIA("A IA devolveu uma resposta fora do formato esperado. Tente gerar de novo.") from erro
    if isinstance(dados, dict):
        dados = dados.get("variacoes") or dados.get("modelos") or [dados]
    itens = [{"assunto": str(d.get("assunto", "")).strip(), "texto": str(d.get("texto", "")).strip()}
             for d in dados if isinstance(d, dict) and d.get("texto")]
    if not itens:
        raise ErroIA("A IA não devolveu nenhum rascunho utilizável. Tente descrever a situação de outra forma.")
    return itens


def avisos_do_modelo(assunto, texto):
    """Checagens automáticas para pegar invenções da IA (ou erros seus) antes de salvar."""
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
