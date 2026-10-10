"""Leitura da planilha e triagem (quem pode ou não receber) — antes de enviar qualquer coisa."""
from dataclasses import dataclass, field

import pandas as pd

from .colunas import registro_da_linha
from .utils import email_valido


def carregar_dataframe(arquivo):
    """Lê xlsx/xls/csv/txt tentando codificações e separadores comuns (arquivo no formato do upload do Streamlit)."""
    nome = arquivo.name.lower()
    if nome.endswith((".xlsx", ".xls")):
        try:
            return pd.read_excel(arquivo)
        except Exception:
            arquivo.seek(0)
            return pd.read_csv(arquivo, sep="\t", encoding="latin1")
    for codificacao in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
        for sep in (None, "\t", ";", ","):
            try:
                arquivo.seek(0)
                if sep is None:
                    df = pd.read_csv(arquivo, sep=None, engine="python", encoding=codificacao)
                else:
                    df = pd.read_csv(arquivo, sep=sep, encoding=codificacao)
                if len(df.columns) > 1 and len(df) > 0:
                    return df
            except Exception:
                continue
    arquivo.seek(0)
    return pd.read_csv(arquivo, on_bad_lines="skip")


def limpar_dataframe(df):
    df = df.dropna(how="all").reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    return df


class Triagem:
    """Decide, linha a linha, se o e-mail deve ser ignorado. Devolve o motivo ou None (pode enviar)."""

    def __init__(self, descadastrados, ja_enviados, permitir_reenvio=False):
        self.descadastrados = set(descadastrados)
        self.ja_enviados = set(ja_enviados)
        self.permitir_reenvio = permitir_reenvio
        self._vistos = set()

    def motivo(self, protocolo, email):
        chave = f"{protocolo}|{email}"
        if not email_valido(email):
            return "IGNORADO: e-mail inválido/fictício"
        if email in self.descadastrados:
            return "IGNORADO: cliente pediu para sair (descadastrado)"
        if chave in self._vistos:
            return "IGNORADO: duplicado na planilha"
        if not self.permitir_reenvio and chave in self.ja_enviados:
            return "IGNORADO: já enviado anteriormente"
        self._vistos.add(chave)
        return None


@dataclass
class RelatorioPrevio:
    total: int = 0
    enviaveis: int = 0
    motivos: dict = field(default_factory=dict)


def relatorio_previo(df, mapa, descadastrados, ja_enviados, permitir_reenvio=False):
    """Conta quantos e-mails sairão e por que os demais serão pulados."""
    triagem = Triagem(descadastrados, ja_enviados, permitir_reenvio)
    rel = RelatorioPrevio(total=len(df))
    for _, linha in df.iterrows():
        reg = registro_da_linha(linha, mapa)
        motivo = triagem.motivo(reg["protocolo"], reg["email"])
        if motivo is None:
            rel.enviaveis += 1
        else:
            rel.motivos[motivo] = rel.motivos.get(motivo, 0) + 1
    return rel
