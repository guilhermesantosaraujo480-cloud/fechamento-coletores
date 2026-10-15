"""Perfil = como ler a planilha de cada empresa (nomes das colunas) e como montar a planilha de saída."""
from dataclasses import dataclass, field

CAMPOS = {
    "id": "Protocolo / pedido (BA)", "conta": "Conta", "nome": "Nome do cliente", "endereco": "Endereço (rua)",
    "numero": "Número", "bairro": "Bairro", "cep": "CEP", "cidade": "Cidade", "uf": "UF",
    "telefone": "Telefone 1", "telefone2": "Telefone 2 / Celular", "complemento": "Complemento / informação",
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

PERFIS_PADRAO = [REINTEGRA, TIM_CSS]


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
