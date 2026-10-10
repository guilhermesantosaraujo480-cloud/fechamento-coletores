"""Cliques no botão do WhatsApp: separa PESSOAS de ROBÔS (scanners de segurança dos provedores de e-mail).

Sinais de robô: user agent típico de robô; 3+ cliques do mesmo envio em até 10 s; clique menos de 20 s após o envio.
Os nomes das colunas variam, então tudo é detectado de forma tolerante.
"""
from dataclasses import dataclass

import pandas as pd

PADROES_ROBO = (
    "bot", "crawler", "spider", "scanner", "preview", "googleimageproxy", "google-safety", "proofpoint",
    "mimecast", "barracuda", "symantec", "trend micro", "python-requests", "python-urllib", "curl/", "wget",
    "headless", "go-http-client", "java/", "libwww", "httpclient", "node-fetch", "axios", "ahrefs", "facebookexternalhit",
)
COLUNAS_UA = ("user_agent", "useragent", "user-agent", "ua", "agent")
COLUNAS_TEMPO = ("data_hora", "created_at", "criado_em", "clicked_at", "timestamp", "data")
JANELA_RAJADA_SEG = 10
CLIQUES_RAJADA = 3
ATRASO_MINIMO_HUMANO_SEG = 20


@dataclass
class ResumoCliques:
    total: int = 0
    robos: int = 0
    pessoas: int = 0
    envios_com_pessoa: int = 0
    taxa_pessoas: float = 0.0  # % dos e-mails enviados com ao menos um clique de pessoa


def _primeira_coluna(df, candidatas):
    minusculas = {str(c).lower(): c for c in df.columns}
    return next((minusculas[c] for c in candidatas if c in minusculas), None)


def classificar_cliques(cliques, envios=None):
    """Devolve cópia do DataFrame com as colunas `perfil` (Pessoa/Robô) e `motivo`."""
    df = cliques.copy()
    df["perfil"], df["motivo"] = "Pessoa", ""
    if df.empty:
        return df

    col_ua = _primeira_coluna(df, COLUNAS_UA)
    if col_ua:
        ua = df[col_ua].fillna("").astype(str).str.lower()
        bate = ua.map(lambda s: next((p for p in PADROES_ROBO if p in s), ""))
        df.loc[bate != "", "perfil"] = "Robô"
        df.loc[bate != "", "motivo"] = "user agent: " + bate[bate != ""]

    col_t = _primeira_coluna(df, COLUNAS_TEMPO)
    if col_t and "envio_id" in df.columns:
        df["_t"] = pd.to_datetime(df[col_t], utc=True, errors="coerce")
        for _, grupo in df.dropna(subset=["_t"]).groupby("envio_id"):
            tempos = grupo["_t"].sort_values()
            if len(tempos) >= CLIQUES_RAJADA:
                valores = list(tempos)
                for i in range(len(valores) - CLIQUES_RAJADA + 1):
                    if (valores[i + CLIQUES_RAJADA - 1] - valores[i]).total_seconds() <= JANELA_RAJADA_SEG:
                        idx = tempos.index[i:i + CLIQUES_RAJADA]
                        sem_motivo = df.loc[idx, "motivo"] == ""
                        df.loc[idx[sem_motivo.values], "motivo"] = "rajada de cliques"
                        df.loc[idx, "perfil"] = "Robô"
        if envios is not None and not envios.empty and {"envio_id", "data_hora"} <= set(envios.columns):
            saida = envios.drop_duplicates("envio_id").set_index("envio_id")["data_hora"]
            saida = pd.to_datetime(saida, utc=True, errors="coerce")
            atraso = (df["_t"] - df["envio_id"].map(saida)).dt.total_seconds()
            rapido = (atraso >= 0) & (atraso < ATRASO_MINIMO_HUMANO_SEG) & (df["perfil"] == "Pessoa")
            df.loc[rapido, "perfil"] = "Robô"
            df.loc[rapido, "motivo"] = "clique logo após o envio"
        df = df.drop(columns=["_t"])
    return df


def resumir(cliques_classificados, total_enviados=0):
    df = cliques_classificados
    if df.empty:
        return ResumoCliques()
    pessoas = df[df["perfil"] == "Pessoa"]
    envios = pessoas["envio_id"].nunique() if "envio_id" in pessoas.columns else len(pessoas)
    taxa = round(100 * envios / total_enviados, 1) if total_enviados else 0.0
    return ResumoCliques(total=len(df), robos=int((df["perfil"] == "Robô").sum()), pessoas=len(pessoas),
                         envios_com_pessoa=int(envios), taxa_pessoas=taxa)
