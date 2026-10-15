"""Liga o nome que vem na planilha da plataforma ('GUILHERME SANTOS ARAUJO', 'Renilton Araujo da Cunha (Coletor)')
ao coletor da rota ('GUILHERME', 'RENILTON'). Ordem: apelido salvo > nome igual > primeiro nome."""
import re
from collections import Counter

from .processamento import SEM_COLETOR, chave_texto

TIPOS = ("normal", "retentativa", "deposito")
ROTULO_TIPO = {"normal": "Normal (recebe rota)", "retentativa": "Retentativas (OS que já foram à rua)",
               "deposito": "Depósito (OS paradas, não trabalha)"}


def normalizar_nome(texto):
    """'Renilton Araujo da Cunha (Coletor)' -> 'RENILTON ARAUJO DA CUNHA'; 'ARLEIDE.JULIENE' -> 'ARLEIDE JULIENE'."""
    t = re.sub(r"\([^)]*\)", " ", str(texto or ""))
    t = re.sub(r"[._\-/]+", " ", t)
    return chave_texto(re.sub(r"[^\w\s]", " ", t))


def _tokens(texto):
    return [x for x in normalizar_nome(texto).split() if x]


def casar(nome_planilha, coletores, apelidos=None):
    """-> (nome_rota | None, origem). origem: 'apelido' | 'nome' | 'primeiro nome' | 'ambíguo' | 'sem correspondência'."""
    norm = normalizar_nome(nome_planilha)
    if not norm:
        return None, "vazio"
    apelidos = apelidos or {}
    if norm in apelidos and apelidos[norm] in coletores:
        return apelidos[norm], "apelido"
    for c in coletores:
        if normalizar_nome(c) == norm:
            return c, "nome"
    sheet = norm.split()
    candidatos = []
    for c in coletores:
        cand = set(_tokens(c))
        if cand and sheet[0] in cand:  # o primeiro nome da pessoa tem que ser um dos nomes do coletor
            candidatos.append((len(cand & set(sheet)), -len(cand), c))
    if not candidatos:
        return None, "sem correspondência"
    candidatos.sort(reverse=True)
    melhores = [c for c in candidatos if c[:2] == candidatos[0][:2]]
    if len(melhores) > 1:
        return None, "ambíguo"
    return candidatos[0][2], "primeiro nome"


def mapear(serie, coletores, apelidos=None):
    """Tabela de conferência: um registro por nome diferente que aparece na planilha."""
    contagem = Counter(str(v).strip() for v in serie if str(v or "").strip())
    linhas = []
    for bruto, qtd in contagem.most_common():
        rota, origem = casar(bruto, coletores, apelidos)
        linhas.append({"bruto": bruto, "rota": rota, "origem": origem, "qtd": qtd})
    return linhas


def atribuir(serie, coletores, apelidos=None, ajustes=None):
    """Série com o nome do coletor da rota para cada OS (SEM_COLETOR quando vazio/desconhecido).
    ajustes: {nome_bruto: nome_rota} escolhidos na tela para esta planilha."""
    ajustes = ajustes or {}
    cache = {}
    saida = []
    for v in serie:
        bruto = str(v or "").strip()
        if not bruto:
            saida.append(SEM_COLETOR)
            continue
        if bruto not in cache:
            cache[bruto] = ajustes.get(bruto) or casar(bruto, coletores, apelidos)[0] or SEM_COLETOR
        saida.append(cache[bruto])
    return saida
