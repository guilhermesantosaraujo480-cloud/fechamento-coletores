"""Transforma a planilha da operadora em rota: limpa, confere, ordena e divide entre coletores. Tudo puro (pandas)."""
import re
import urllib.parse

import pandas as pd

from .perfis import CAMPOS

SEM_COLETOR = "(sem coletor)"


def limpar(valor):
    if valor is None or valor != valor:
        return ""
    s = str(valor).strip()
    if s.lower() in ("nan", "none", "null", "nat"):
        return ""
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s


def normalizar_telefone(valor):
    """(texto formatado, válido?). '5511987654321' -> '(11) 98765-4321'."""
    original = limpar(valor)
    d = re.sub(r"\D", "", original)
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if d.startswith("0") and len(d) in (11, 12):
        d = d[1:]
    if len(d) == 11 and d[2] == "9" and d[0] != "0":
        return f"({d[:2]}) {d[2:7]}-{d[7:]}", True
    if len(d) == 10 and d[0] != "0" and d[2] in "2345":
        return f"({d[:2]}) {d[2:6]}-{d[6:]}", True
    return original, False


def normalizar_cep(valor):
    d = re.sub(r"\D", "", limpar(valor))
    if len(d) == 7:  # o Excel come o zero da frente
        d = "0" + d
    return (f"{d[:5]}-{d[5:]}", True) if len(d) == 8 else (limpar(valor), False)


def link_mapa(endereco, bairro, cidade, uf, cep):
    partes = [p for p in (endereco, bairro, cidade, uf, cep) if p]
    if not endereco:
        return ""
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(", ".join(partes))


def aplicar_perfil(df, perfil):
    """Devolve (DataFrame com campos padronizados, colunas do perfil que não existem na planilha)."""
    colunas = {str(c).strip().lower(): c for c in df.columns}
    can, faltando = pd.DataFrame(index=df.index), []
    for campo in CAMPOS:
        origem = perfil.mapa.get(campo)
        coluna = colunas.get(str(origem).strip().lower()) if origem else None
        if origem and coluna is None:
            faltando.append(origem)
        can[campo] = df[coluna].map(limpar) if coluna is not None else ""
    can["endereco_completo"] = [f"{e} N° {n}" if e and n else e for e, n in zip(can["endereco"], can["numero"])]
    tel1 = can["telefone"].map(normalizar_telefone)
    tel2 = can["telefone2"].map(normalizar_telefone)
    can["telefone"], can["telefone2"] = tel1.map(lambda x: x[0]), tel2.map(lambda x: x[0])
    can["tel_ok"] = [a[1] or b[1] for a, b in zip(tel1, tel2)]
    cep = can["cep"].map(normalizar_cep)
    can["cep"], can["cep_ok"] = cep.map(lambda x: x[0]), cep.map(lambda x: x[1])
    can["mapa"] = [link_mapa(e, b, c, u, p) for e, b, c, u, p in
                   zip(can["endereco_completo"], can["bairro"], can["cidade"], can["uf"], can["cep"])]
    vazias = (can["id"] == "") & (can["nome"] == "") & (can["endereco"] == "")
    return can[~vazias], faltando


def checar_qualidade(can):
    """Tabela de problemas que merecem olhar antes de mandar para o coletor."""
    achados = []
    repetidos = set(can.loc[(can["id"] != "") & can["id"].duplicated(keep=False), "id"])
    mesmo_local = can[(can["endereco_completo"] != "")].groupby(["endereco_completo", "cep"]).size()
    mesmo_local = {k for k, v in mesmo_local.items() if v > 1}
    for idx, r in can.iterrows():
        def add(texto, grave=True):
            achados.append({"Linha": idx + 2, "ID": r["id"], "Cliente": r["nome"], "Problema": texto,
                            "Gravidade": "⚠️" if grave else "ℹ️"})
        if not r["endereco"]:
            add("Sem endereço")
        if not r["tel_ok"]:
            add("Sem telefone válido")
        if not r["bairro"]:
            add("Sem bairro")
        if r["cep"] and not r["cep_ok"]:
            add("CEP inválido", grave=False)
        if r["id"] in repetidos:
            add("ID repetido na planilha")
        if (r["endereco_completo"], r["cep"]) in mesmo_local:
            add("Mesmo endereço de outro cliente (talvez seja a mesma parada)", grave=False)
    return pd.DataFrame(achados, columns=["Linha", "ID", "Cliente", "Problema", "Gravidade"])


def ordenar_rota(can):
    """Agrupa por cidade/bairro e ordena por CEP, rua e número: a ordem natural de percurso."""
    def num(v):
        m = re.search(r"\d+", str(v))
        return int(m.group()) if m else 0
    chave = can.assign(_c=can["cidade"].str.upper(), _b=can["bairro"].str.upper(), _n=can["numero"].map(num))
    return can.loc[chave.sort_values(["_c", "_b", "cep", "endereco", "_n"]).index]


def dividir_entre(can, coletores):
    """Divide a rota entre os coletores mantendo cada bairro junto e a carga equilibrada.
    Bairro muito grande (mais de 30% acima da cota) é repartido por CEP."""
    atrib = pd.Series(SEM_COLETOR, index=can.index, dtype=object)
    coletores = list(coletores)
    if not coletores or can.empty:
        return atrib
    cota = -(-len(can) // len(coletores))
    pedacos = []
    for _, grupo in can.groupby([can["cidade"].str.upper(), can["bairro"].str.upper()], sort=True):
        grupo = grupo.sort_values(["cep", "endereco"])
        if len(grupo) > cota * 1.3:
            pedacos += [grupo.iloc[i:i + cota] for i in range(0, len(grupo), cota)]
        else:
            pedacos.append(grupo)
    carga = {c: 0 for c in coletores}
    for p in sorted(pedacos, key=len, reverse=True):
        c = min(carga, key=lambda k: (carga[k], coletores.index(k)))
        atrib.loc[p.index] = c
        carga[c] += len(p)
    return atrib


def montar_saida(can, perfil, incluir_mapa=True):
    """Planilha final no mesmo formato dos scripts antigos (+ coluna 'Mapa', opcional)."""
    saida = pd.DataFrame({cab: can[campo] for cab, campo in perfil.saida})
    if incluir_mapa:
        saida["Mapa"] = can["mapa"]
    return saida.reset_index(drop=True)


def numero_whatsapp(telefone):
    """Só dígitos, com DDI 55 quando for número brasileiro de 10/11 dígitos."""
    d = re.sub(r"\D", "", str(telefone or ""))
    if d.startswith("0"):
        d = d.lstrip("0")
    if len(d) in (10, 11):
        d = "55" + d
    return d
