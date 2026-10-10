"""Reconhece automaticamente as colunas da planilha (BA/Protocolo, Cliente, Email, Endereço...)."""
import re
import unicodedata

CAMPOS = {
    "protocolo": ["ba", "protocolo", "protocol", "os", "ordem de servico", "n protocolo"],
    "nome": ["cliente", "nome", "nome do cliente", "nome completo"],
    "email": ["email", "e mail", "mail", "email do cliente"],
    "endereco": ["endereco", "logradouro", "rua"],
    "numero": ["numero", "num", "n", "nro"],
    "bairro": ["bairro"],
    "cep": ["cep"],
    "tipo": ["tipo", "tipo cancelamento", "tipo de cancelamento", "tipo_cancelamento"],
}
ROTULOS = {
    "protocolo": "Protocolo (BA)", "nome": "Nome do cliente", "email": "E-mail", "endereco": "Endereço",
    "numero": "Número", "bairro": "Bairro", "cep": "CEP", "tipo": "Tipo de cancelamento",
}
OBRIGATORIOS = ("email",)


def normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def detectar_colunas(df):
    """{campo: nome_da_coluna_na_planilha ou None}."""
    por_nome = {normalizar(c): c for c in df.columns}
    mapa = {}
    for campo, apelidos in CAMPOS.items():
        mapa[campo] = next((por_nome[normalizar(a)] for a in apelidos if normalizar(a) in por_nome), None)
    return mapa


def valor_celula(valor):
    """Texto limpo de uma célula (NaN/None/'nan' viram ''; '123.0' vira '123')."""
    if valor is None or valor != valor:
        return ""
    s = str(valor).strip()
    if s.lower() in ("nan", "none", "null", "nat"):
        return ""
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s


def registro_da_linha(linha, mapa):
    reg = {}
    for campo in CAMPOS:
        coluna = mapa.get(campo)
        reg[campo] = valor_celula(linha[coluna]) if coluna is not None and coluna in linha.index else ""
    reg["email"] = reg["email"].lower()
    return reg


def montar_endereco(reg):
    partes = []
    if reg.get("endereco"):
        partes.append(reg["endereco"])
    if reg.get("numero"):
        partes.append(f"Nº {reg['numero']}")
    if reg.get("bairro"):
        partes.append(reg["bairro"])
    if reg.get("cep"):
        partes.append(f"CEP: {reg['cep']}")
    return " - ".join(partes) if partes else "Endereço incompleto na planilha"


def tipo_cancelamento(reg):
    bruto = (reg.get("tipo") or "").lower()
    if "involunt" in bruto:
        return "involuntario"
    if "volunt" in bruto:
        return "voluntario"
    return "padrao"
