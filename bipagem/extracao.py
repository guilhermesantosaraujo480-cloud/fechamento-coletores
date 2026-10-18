"""Extrai os números de série (e a OS) do PDF das ordens de serviço — mesma regra do localizador_os.py:
12 caracteres de 0-9/A-F com pelo menos uma letra. Agora guarda também a OS e a página."""
import re
import unicodedata

PADRAO_SERIAL = re.compile(r"\b[0-9A-F]{12}\b")
PADRAO_OS = re.compile(r"\bOS\s+([A-Z0-9]+(?:-[A-Z0-9]+)+)", re.IGNORECASE)


def seriais_do_texto(texto):
    """Seriais da página, na ordem em que aparecem, sem repetir. Número só com dígitos (telefone, CEP) não conta."""
    vistos, saida = set(), []
    for s in PADRAO_SERIAL.findall(texto or ""):
        if not s.isdigit() and s not in vistos:
            vistos.add(s)
            saida.append(s)
    return saida


def os_do_texto(texto):
    achou = PADRAO_OS.search(texto or "")
    return achou.group(1).upper() if achou else ""


def registros_da_pagina(numero, texto):
    """Um registro por serial; página sem serial gera um registro com serial vazio (para o site avisar)."""
    os_ = os_do_texto(texto)
    seriais = seriais_do_texto(texto)
    if not seriais:
        return [{"pagina": numero, "os": os_, "serial": ""}]
    return [{"pagina": numero, "os": os_, "serial": s} for s in seriais]


def extrair_pdf(origem, progresso=None):
    """`origem`: caminho ou arquivo aberto. `progresso(pagina, total)` é chamado de tempos em tempos."""
    from pypdf import PdfReader  # só é preciso para PDF
    leitor = PdfReader(origem)
    total = len(leitor.pages)
    registros = []
    for i, pagina in enumerate(leitor.pages, start=1):
        try:
            texto = pagina.extract_text() or ""
        except Exception:  # página corrompida: segue com as outras
            texto = ""
        registros.extend(registros_da_pagina(i, texto))
        if progresso and (i == total or i % 25 == 0):
            progresso(i, total)
    return registros


def extrair_paginas_texto(paginas):
    """Mesma extração, a partir de uma lista de textos (uma por página). Usado nos testes."""
    registros = []
    for i, texto in enumerate(paginas, start=1):
        registros.extend(registros_da_pagina(i, texto))
    return registros


def seriais_unicos(registros):
    """Seriais na ordem do PDF, sem repetir."""
    vistos, saida = set(), []
    for r in registros:
        s = r["serial"]
        if s and s not in vistos:
            vistos.add(s)
            saida.append(s)
    return saida


def resumir(registros):
    paginas = {r["pagina"] for r in registros}
    sem = [r for r in registros if not r["serial"]]
    contagem = {}
    for r in registros:
        if r["serial"]:
            contagem.setdefault(r["serial"], []).append(r["os"] or f"pág. {r['pagina']}")
    repetidos = {s: oss for s, oss in contagem.items() if len(oss) > 1}
    return {"paginas": len(paginas), "seriais": len(contagem), "sem_serial": sem, "repetidos": repetidos}


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn").lower().strip()


def ler_planilha(origem):
    """Planilha com os seriais (coluna 'Numero', como no Os_automação.xlsx; senão, a primeira coluna)."""
    import pandas as pd
    df = pd.read_excel(origem, dtype=str)
    if df.empty:
        return []
    coluna = next((c for c in df.columns if _sem_acento(c) in ("numero", "serial", "numero de serie")), df.columns[0])
    saida = []
    for v in df[coluna].tolist():
        v = "" if v is None or v != v else str(v).strip()
        if v:
            saida.append(v)
    return saida
