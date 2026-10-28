"""Perfil = como ler a planilha de cada empresa (nomes das colunas) e como montar a planilha de saída."""
from dataclasses import dataclass, field

CAMPOS = {
    "id": "Protocolo / pedido (BA)", "conta": "Conta", "nome": "Nome do cliente", "endereco": "Endereço (rua)",
    "numero": "Número", "bairro": "Bairro", "cep": "CEP", "cidade": "Cidade", "uf": "UF",
    "telefone": "Telefone 1", "telefone2": "Telefone 2 / Celular", "complemento": "Complemento / informação",
    # Campos opcionais (empresas de entrega de chip, como a Toolbox). Ficam no fim: os perfis antigos não os usam.
    "cpf": "CPF/CNPJ do cliente", "pais": "País", "itens": "Descrição dos itens (ex.: HLR / NAKED)",
}

# Nomes que costumam aparecer nas planilhas de cada campo (sugestão automática na tela "Cadastrar nova empresa").
APELIDOS_COLUNA = {
    "id": ["pedido", "numero do pedido", "ba", "protocolo", "id", "os"],
    "conta": ["conta"],
    "nome": ["nome", "cliente", "nome do cliente"],
    "endereco": ["logradouro", "endereco", "rua"],
    "numero": ["numero", "num", "n"],
    "bairro": ["bairro"],
    "cep": ["cep"],
    "cidade": ["cidade", "municipio"],
    "uf": ["uf", "estado"],
    "telefone": ["telefone", "telefone 1", "fone", "tel"],
    "telefone2": ["celular", "telefone 2", "whatsapp"],
    "complemento": ["complemento", "informacao adicional", "referencia"],
    "cpf": ["cpf/cnpj", "cpf cnpj", "cpf", "cnpj"],
    "pais": ["pais"],
    "itens": ["descricao dos itens", "itens", "produto"],
}


# Campos extras (opcionais): não entram na planilha de saída, servem para avisos, distribuição e acompanhamento.
# Se a planilha não tiver a coluna, o campo simplesmente fica vazio (nunca dá erro).
EXTRAS = {
    "coletor": "Coletor já definido na plataforma", "tipo_os": "Voluntário / Involuntário", "agenda": "Data de agenda",
    "status_agenda": "Status do agendamento", "tentativas": "Nº de agendamentos/tentativas", "backlog": "Dias na fila",
    "motivo": "Último motivo / ocorrência", "ocorrencia": "Descrição da ocorrência", "prioridade": "Prioridade",
    "reaberta": "Reaberta em",
}


def _n(texto):
    return str(texto).strip().lower()


def _chave_coluna(nome):
    """'Destino - Informação adicional' -> ('informacao adicional', 0). O 2º valor é a prioridade do prefixo:
    Destino (0) vence sem prefixo (1), que vence Origem (2) — a rota vai para onde o equipamento/chip VAI."""
    import re
    import unicodedata
    sem = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().lower().strip()
    m = re.match(r"^(destino|origem)\s*-\s*(.+)$", sem)
    if m:
        return m.group(2).strip(), 0 if m.group(1) == "destino" else 2
    return re.sub(r"\s+", " ", sem), 1


def sugerir_coluna(campo, colunas):
    """Coluna da planilha que melhor combina com o campo (None se nenhuma). Ignora prefixos 'Destino - ' / 'Origem - '."""
    candidatas = [(_chave_coluna(c), c) for c in colunas]
    for apelido in APELIDOS_COLUNA.get(campo, [campo]):
        achadas = sorted((prio, c) for (chave, prio), c in candidatas if chave == apelido)
        if achadas:
            return achadas[0][1]
    return None


@dataclass
class Perfil:
    nome: str
    sufixo: str                                   # vai no nome do arquivo: Rota_X_data_<sufixo>.xlsx
    mapa: dict                                    # campo -> nome da coluna na planilha da empresa
    saida: list                                   # [(cabeçalho, campo | "endereco_completo")]
    assinatura: list = field(default_factory=list)  # colunas que só essa empresa tem (detecção automática)
    padrao: bool = False
    extras: dict = field(default_factory=dict)    # campo extra -> coluna (opcional, ver EXTRAS)

    def para_dict(self):
        return {"nome": self.nome, "sufixo": self.sufixo, "mapa": self.mapa,
                "saida": [list(x) for x in self.saida], "assinatura": self.assinatura, "extras": self.extras}

    @staticmethod
    def de_dict(d, padrao=False):
        return Perfil(d["nome"], d["sufixo"], dict(d["mapa"]), [tuple(x) for x in d["saida"]],
                      list(d.get("assinatura", [])), padrao, dict(d.get("extras") or {}))


REINTEGRA = Perfil(
    nome="Reintegra", sufixo="EMPRESA REINTEGRA", padrao=True,
    mapa={"id": "BA", "nome": "Cliente", "endereco": "Endereço", "numero": "Número", "bairro": "Bairro", "cep": "Cep",
          "cidade": "Cidade", "uf": "UF", "telefone": "Telefone 1", "complemento": "Complemento"},
    saida=[("BA", "id"), ("Cliente", "nome"), ("Endereço completo", "endereco_completo"), ("Bairro", "bairro"),
           ("Cep", "cep"), ("Cidade", "cidade"), ("Telefone 1", "telefone"), ("Complemento", "complemento"), ("UF", "uf")],
    assinatura=["BA", "Cliente", "Endereço", "Telefone 1"],
    extras={"coletor": "Coletor", "tipo_os": "Tipo", "agenda": "Agenda", "tentativas": "Qtd Ag.", "backlog": "Backlog",
            "motivo": "Ultimo Motivo/Ocorrencia", "ocorrencia": "Descrição Ocorrência"},
)

TIM_CSS = Perfil(
    nome="TIM (CSS)", sufixo="EMPRESA CSS", padrao=True,
    mapa={"id": "Número do Pedido", "conta": "Conta.2", "nome": "Nome", "endereco": "Logradouro", "numero": "Número",
          "bairro": "Bairro", "cep": "CEP", "cidade": "Cidade", "uf": "UF", "telefone": "Telefone",
          "telefone2": "Celular", "complemento": "Informação adicional"},
    saida=[("Número do Pedido", "id"), ("Conta.2", "conta"), ("Nome", "nome"), ("Endereço completo", "endereco_completo"),
           ("Bairro", "bairro"), ("CEP", "cep"), ("Cidade", "cidade"), ("Telefone", "telefone"),
           ("Celular", "telefone2"), ("Informação adicional", "complemento"), ("UF", "uf")],
    assinatura=["Número do Pedido", "Conta.2", "Logradouro"],
    extras={"coletor": "Transportador.1", "tipo_os": "Voluntário?", "agenda": "Agendamento para até",
            "status_agenda": "Status de Agendamento", "reaberta": "Reaberto em", "prioridade": "Descrição da Prioridade",
            "ocorrencia": "Descrição da Ocorrência"},
)

# Toolbox (TIM Blue Chip): entrega de CHIPS. A planilha vem do sistema com colunas "Destino - ...", e o arquivo de saída segue o
# modelo ROTA_TIM.xlsx (números sem pontuação, cidade em maiúsculas, tipo do chip HLR/NAKED no fim).
TOOLBOX = Perfil(
    nome="Toolbox (chips)", sufixo="EMPRESA TOOLBOX", padrao=True,
    mapa={"id": "Pedido", "nome": "Destino - Nome", "endereco": "Destino - Logradouro", "numero": "Destino - Número",
          "bairro": "Destino - Bairro", "cep": "Destino - CEP", "cidade": "Destino - Cidade", "uf": "Destino - UF",
          "telefone": "Destino - Telefone", "telefone2": "Destino - Celular", "complemento": "Destino - Informação adicional",
          "cpf": "Destino - CPF/CNPJ", "pais": "Destino - País", "itens": "Descrição dos itens"},
    saida=[("Pedido", "id"), ("Destino - Nome", "nome"), ("Destino - CPF/CNPJ", "cpf"), ("Destino - Celular", "celular_num"),
           ("Endereço Completo", "endereco_completo"), ("Destino - Bairro", "bairro"), ("Destino - Cidade", "cidade_up"),
           ("Destino - CEP", "cep_num"), ("Destino - UF", "uf"), ("Destino - País", "pais"),
           ("Destino - Informação adicional", "complemento"), ("Descrição dos itens", "itens")],
    assinatura=["Pedido", "Destino - Nome", "Destino - Logradouro", "Descrição dos itens"],
    extras={"tipo_os": "Tipo", "status_agenda": "Status de Agendamento", "agenda": "Agendamento para até",
            "coletor": "Transportador", "tentativas": "Tentativas", "prioridade": "Prioridade"},
)

PERFIS_PADRAO = [REINTEGRA, TIM_CSS, TOOLBOX]


def detectar_perfil(colunas, perfis):
    """Perfil cuja assinatura mais bate com as colunas da planilha (None se nenhum bater por inteiro)."""
    presentes = {_n(c) for c in colunas}
    melhor, melhor_nota = None, 0.0
    for p in perfis:
        if not p.assinatura:
            continue
        nota = sum(_n(a) in presentes for a in p.assinatura) / len(p.assinatura)
        if nota > melhor_nota:
            melhor, melhor_nota = p, nota
    return melhor if melhor_nota >= 0.99 else None


def perfil_a_partir_do_mapa(nome, sufixo, mapa, extras=None):
    """Cria um perfil novo (empresa nova) a partir das colunas escolhidas na tela."""
    mapa = {k: v for k, v in mapa.items() if v}
    extras = {k: v for k, v in (extras or {}).items() if v}
    saida = []
    for campo, rotulo in CAMPOS.items():
        if campo == "numero":
            continue
        if campo == "endereco":
            saida.append(("Endereço completo", "endereco_completo"))
        elif campo in mapa:
            saida.append((mapa[campo], campo))
    assinatura = [v for k, v in mapa.items() if k in ("id", "nome", "endereco")]
    return Perfil(nome.strip(), sufixo.strip() or f"EMPRESA {nome.strip().upper()}", mapa, saida, assinatura, extras=extras)
