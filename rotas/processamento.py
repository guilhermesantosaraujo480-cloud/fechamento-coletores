"""Transforma a planilha da operadora em rota: limpa, confere, ordena e divide entre coletores. Tudo puro (pandas)."""
import re
import unicodedata
import urllib.parse

import pandas as pd

from .perfis import CAMPOS, EXTRAS

SEM_COLETOR = "(sem coletor)"
TIPOS_CHIP = ("HLR", "NAKED")
BAIRROS_GENERICOS = {"", "BAIRRO", "CENTRO NAO INFORMADO", "NAO INFORMADO", "N A", "NA"}


def chave_texto(valor):
    """MAIÚSCULAS sem acento e sem espaços repetidos: 'São  Paulo' e 'SAO PAULO' viram a mesma chave."""
    sem = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem.upper()).strip()


def data_da_planilha(valor):
    """'14/10/2026' ou '14/10/2026 00:00:00' -> date (None se vazio/inválido)."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", str(valor or ""))
    if not m:
        return None
    try:
        from datetime import date
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def inteiro(valor, padrao=0):
    m = re.search(r"-?\d+", str(valor or ""))
    return int(m.group()) if m else padrao


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
    # Formatos "só números" e cidade em maiúsculas (usados pelo perfil Toolbox; os outros perfis não os usam)
    can["celular_num"] = [(numero_do_celular(b) or numero_do_celular(a))[2:] or limpar(b or a) for a, b in zip(can["telefone"], can["telefone2"])]
    can["cep_num"] = can["cep"].map(lambda v: re.sub(r"\D", "", v))
    can["cidade_up"] = can["cidade"].map(lambda v: re.sub(r"\s+", " ", v).strip().upper())
    can["itens"] = can["itens"].map(lambda v: re.sub(r"\s+", " ", v).strip().upper())
    can["mapa"] = [link_mapa(e, b, c, u, p) for e, b, c, u, p in
                   zip(can["endereco_completo"], can["bairro"], can["cidade"], can["uf"], can["cep"])]
    for campo in EXTRAS:  # campos extras: opcionais; coluna ausente = vazio, nunca é erro
        origem = perfil.extras.get(campo)
        coluna = colunas.get(str(origem).strip().lower()) if origem else None
        can[campo] = df[coluna].map(limpar) if coluna is not None else ""
    can["agenda_dt"] = can["agenda"].map(data_da_planilha)
    can["tentativas_n"] = can["tentativas"].map(inteiro)
    can["backlog_n"] = can["backlog"].map(inteiro)
    can["bairro_ef"] = bairro_efetivo(can)
    vazias = (can["id"] == "") & (can["nome"] == "") & (can["endereco"] == "")
    return can[~vazias], faltando


def bairro_efetivo(can):
    """Bairro para agrupar. Se o campo está vazio ou traz o nome da cidade/'bairro' (dado sujo), usa o prefixo do CEP."""
    saida = []
    for b, c, cep in zip(can["bairro"], can["cidade"], can["cep"]):
        kb, kc = chave_texto(b), chave_texto(c)
        if kb in BAIRROS_GENERICOS or kb == kc:
            digitos = re.sub(r"\D", "", cep or "")
            saida.append(f"CEP {digitos[:5]}" if len(digitos) >= 5 else "SEM BAIRRO")
        else:
            saida.append(kb)
    return pd.Series(saida, index=can.index, dtype=object)


def checar_qualidade(can):
    """Tabela de problemas que merecem olhar antes de mandar para o coletor."""
    achados = []
    tem_itens = "itens" in can and bool((can["itens"] != "").any())  # só empresas de chip (Toolbox) usam este campo
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
        elif r["bairro_ef"].startswith(("CEP ", "SEM ")):
            add("Bairro genérico (igual à cidade): agrupado pelo CEP", grave=False)
        if r["cep"] and not r["cep_ok"]:
            add("CEP inválido", grave=False)
        if tem_itens and r["itens"] not in TIPOS_CHIP:
            add("Tipo do chip não é HLR nem NAKED" + (f" ({r['itens']})" if r["itens"] else " (vazio)"))
        if re.search(r"\b(\w{2,})\s+\1\b", chave_texto(r["endereco"])):
            add("Endereço com palavra repetida (ex.: RUA RUA): confira o logradouro", grave=False)
        if r["id"] in repetidos:
            add("ID repetido na planilha")
        if (r["endereco_completo"], r["cep"]) in mesmo_local:
            add("Mesmo endereço de outro cliente (talvez seja a mesma parada)", grave=False)
    return pd.DataFrame(achados, columns=["Linha", "ID", "Cliente", "Problema", "Gravidade"])


def ordenar_rota(can, urgentes_primeiro=False):
    """Agrupa por cidade/bairro e ordena por CEP, rua e número: a ordem natural de percurso.
    urgentes_primeiro: OS com prioridade máxima / agenda de hoje sobem para o topo (precisa da coluna `urgente`)."""
    def num(v):
        m = re.search(r"\d+", str(v))
        return int(m.group()) if m else 0
    chave = can.assign(_c=can["cidade"].map(chave_texto), _b=can["bairro_ef"], _n=can["numero"].map(num),
                       _u=(~can["urgente"].astype(bool)).astype(int) if (urgentes_primeiro and "urgente" in can) else 0)
    return can.loc[chave.sort_values(["_u", "_c", "_b", "cep", "endereco", "_n"]).index]


def dividir_entre(can, coletores):
    """Divide a rota entre os coletores mantendo cada bairro junto e a carga equilibrada.
    Bairro muito grande (mais de 30% acima da cota) é repartido por CEP."""
    atrib = pd.Series(SEM_COLETOR, index=can.index, dtype=object)
    coletores = list(coletores)
    if not coletores or can.empty:
        return atrib
    cota = -(-len(can) // len(coletores))
    pedacos = []
    for _, grupo in can.groupby([can["cidade"].map(chave_texto), can["bairro_ef"]], sort=True):
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


MENSAGEM_WHATS_PADRAO = "Olá, {cliente}, tudo bem? Estou no seu endereço para retirar o equipamento. Pode me atender?"

# Mensagens prontas (aparecem na lista da tela de Rotas; você pode salvar as suas). Campos aceitos:
# {cliente} primeiro nome · {coletor} · {rua} · {numero} · {bairro} · {cidade} · {protocolo}
MODELOS_WHATS = [
    ("Estou no endereço (padrão)", MENSAGEM_WHATS_PADRAO),
    ("Estou chegando na região", "Olá, {cliente}! Aqui é {coletor}. Estarei na região do {bairro} em breve para retirar o equipamento "
                                 "(protocolo {protocolo}). Você estará no endereço?"),
    ("Confirmar endereço", "Olá, {cliente}, tudo bem? Aqui é {coletor}. Vou passar hoje para retirar o equipamento. "
                           "O endereço é {rua}, {numero}, {bairro}? Pode confirmar?"),
    ("Entrega do chip", "Olá, {cliente}! Aqui é {coletor}, estou a caminho para entregar o seu chip (pedido {protocolo}). "
                        "Tem alguém no endereço {rua}, {numero}?"),
    ("Não encontrei ninguém", "Olá, {cliente}. Passei no endereço {rua}, {numero} e não encontrei ninguém. "
                              "Qual o melhor horário para eu voltar?"),
]
CAMPOS_MENSAGEM = ("{cliente}", "{coletor}", "{rua}", "{numero}", "{bairro}", "{cidade}", "{protocolo}")


def primeiro_nome(nome):
    partes = str(nome or "").strip().split()
    return partes[0].capitalize() if partes else ""


def numero_do_celular(telefone):
    """Dígitos com DDI (55) se for celular brasileiro (11 dígitos, começa com 9 depois do DDD); senão ''.
    Telefone fixo não tem WhatsApp, então não gera link."""
    d = re.sub(r"\D", "", str(telefone or ""))
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) == 11 and d[2] == "9" and d[0] != "0":
        return "55" + d
    return ""


def preencher_mensagem(modelo, cliente="", coletor="", extras=None):
    """Troca os campos {cliente}, {coletor}, {rua}, {numero}, {bairro}, {cidade}, {protocolo} e arruma pontuação/espaços
    (campo vazio não deixa buraco: 'Olá, , tudo bem?' vira 'Olá, tudo bem?')."""
    extras = extras or {}
    valores = {"{cliente}": primeiro_nome(cliente), "{coletor}": str(coletor or "")}
    for k in ("rua", "numero", "bairro", "cidade", "protocolo"):
        valores["{" + k + "}"] = str(extras.get(k, "") or "").strip()
    texto = modelo or MENSAGEM_WHATS_PADRAO
    for chave, valor in valores.items():
        texto = texto.replace(chave, valor)
    texto = re.sub(r"\s{2,}", " ", texto)
    texto = re.sub(r"\s+([,!?.])", r"\1", texto)
    texto = re.sub(r",(?=[,!?.])", "", texto)
    return texto.strip()


def link_whatsapp(telefone, telefone2="", cliente="", coletor="", modelo=None, extras=None):
    """https://wa.me/55DDDNUMERO?text=... usando o primeiro celular válido (telefone, depois telefone2). '' se não houver."""
    numero = numero_do_celular(telefone) or numero_do_celular(telefone2)
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text=" + urllib.parse.quote(preencher_mensagem(modelo, cliente, coletor, extras))


def montar_saida(can, perfil, incluir_mapa=True, incluir_avisos=False, incluir_whats=False, modelo_whats=None, coletor=""):
    """Planilha final no mesmo formato dos scripts antigos (+ colunas opcionais no fim: Mapa, WhatsApp, Avisos).
    A coluna WhatsApp é um link direto para a conversa com o cliente, com a mensagem já escrita."""
    saida = pd.DataFrame({cab: can[campo] for cab, campo in perfil.saida})
    if incluir_mapa:
        saida["Mapa"] = can["mapa"]
    if incluir_whats:
        saida["WhatsApp"] = [link_whatsapp(t1, t2, nome, coletor, modelo_whats,
                                           {"rua": rua, "numero": num, "bairro": bairro, "cidade": cidade, "protocolo": proto})
                             for t1, t2, nome, rua, num, bairro, cidade, proto in
                             zip(can["telefone"], can["telefone2"], can["nome"], can["endereco"], can["numero"], can["bairro"],
                                 can["cidade"], can["id"])]
    if incluir_avisos and "avisos" in can:
        saida["Avisos"] = can["avisos"]
    return saida.reset_index(drop=True)


def numero_whatsapp(telefone):
    """Só dígitos, com DDI 55 quando for número brasileiro de 10/11 dígitos."""
    d = re.sub(r"\D", "", str(telefone or ""))
    if d.startswith("0"):
        d = d.lstrip("0")
    if len(d) in (10, 11):
        d = "55" + d
    return d
