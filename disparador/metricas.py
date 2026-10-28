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


def _norm(v):
    """Chave comparável: texto, sem espaços/chaves, minúsculo ('' se vazio)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    t = str(v).strip().strip("{}").lower()
    return "" if t in ("nan", "none", "null") else t


def ligar_aos_envios(cliques, envios):
    """Liga cada clique ao e-mail enviado, mesmo que o identificador gravado pela Edge Function não seja exatamente o `envio_id`.

    Tenta, nesta ordem: envio_id (ou 'envio') = envio_id do envio; = id do envio; protocolo; e-mail.
    Devolve (cópia dos cliques com `envio_id` já ajustado + coluna `ligacao`, diagnóstico).
    Cliques que não se ligam a nada mantêm o valor original (nada some)."""
    diag = {"total": 0, "ligados": 0, "por_metodo": {}, "sem_ligacao": 0, "colunas": [], "exemplo_clique": "", "exemplo_envio": ""}
    if cliques is None or cliques.empty:
        return (cliques.copy() if cliques is not None else pd.DataFrame()), diag
    df = cliques.copy()
    diag["total"], diag["colunas"] = len(df), [str(c) for c in df.columns]
    df["ligacao"] = ""
    if envios is None or envios.empty or "envio_id" not in envios.columns:
        diag["sem_ligacao"] = len(df)
        return df, diag
    env = envios.drop_duplicates("envio_id")
    por_eid = {_norm(e): e for e in env["envio_id"] if _norm(e)}
    por_id = {_norm(i): e for i, e in zip(env["id"], env["envio_id"])} if "id" in env.columns else {}
    ordenado = envios[envios["status"] == "enviado"] if "status" in envios.columns else envios
    if "data_hora" in ordenado.columns:
        ordenado = ordenado.sort_values("data_hora")
    por_proto, por_email = {}, {}
    for r in ordenado.itertuples():
        eid = getattr(r, "envio_id", "")
        if _norm(getattr(r, "protocolo", "")):
            por_proto[_norm(r.protocolo)] = eid
        if _norm(getattr(r, "email", "")):
            por_email[_norm(r.email)] = eid
    minus = {str(c).lower(): c for c in df.columns}
    col = lambda *nomes: next((minus[n] for n in nomes if n in minus), None)  # noqa: E731
    c_env, c_pro, c_mail = col("envio_id", "envio"), col("protocolo"), col("email", "e-mail")
    novos, metodos = [], []
    for _, linha in df.iterrows():
        valor = _norm(linha[c_env]) if c_env else ""
        achou, metodo = None, ""
        if valor in por_eid:
            achou, metodo = por_eid[valor], "envio_id"
        elif valor in por_id:
            achou, metodo = por_id[valor], "id do envio"
        elif c_pro and _norm(linha[c_pro]) in por_proto:
            achou, metodo = por_proto[_norm(linha[c_pro])], "protocolo"
        elif c_mail and _norm(linha[c_mail]) in por_email:
            achou, metodo = por_email[_norm(linha[c_mail])], "e-mail"
        novos.append(achou if achou is not None else (linha[c_env] if c_env else None))
        metodos.append(metodo)
    df["envio_id"] = novos
    df["ligacao"] = metodos
    contagem = pd.Series(metodos).value_counts()
    diag["por_metodo"] = {k: int(v) for k, v in contagem.items() if k}
    diag["ligados"] = int(sum(diag["por_metodo"].values()))
    diag["sem_ligacao"] = diag["total"] - diag["ligados"]
    if c_env and df[c_env].notna().any():
        diag["exemplo_clique"] = str(df[c_env].dropna().iloc[0])
    diag["exemplo_envio"] = str(env["envio_id"].iloc[0])
    return df, diag


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


def desempenho_por_modelo(envios, cliques_classificados, descadastrados=()):
    """Tabela por modelo: enviados, erros, cliques de PESSOAS, taxa e descadastros.
    envios: DataFrame com envio_id, email, modelo, status. cliques_classificados: saída de classificar_cliques."""
    colunas = ["Modelo", "Enviados", "Erros", "Clicaram (pessoas)", "Taxa de clique", "Descadastros"]
    if envios is None or envios.empty or "modelo" not in envios.columns:
        return pd.DataFrame(columns=colunas)
    df = envios.copy()
    df["modelo"] = df["modelo"].fillna("(sem nome)").replace("", "(sem nome)")
    pessoas = set()
    if cliques_classificados is not None and not cliques_classificados.empty and "envio_id" in cliques_classificados.columns:
        pessoas = set(cliques_classificados.loc[cliques_classificados["perfil"] == "Pessoa", "envio_id"].dropna())
    sair = {str(e).lower() for e in descadastrados}
    linhas = []
    for modelo, grupo in df.groupby("modelo"):
        ok = grupo[grupo["status"] == "enviado"]
        clicaram = int(ok["envio_id"].isin(pessoas).sum()) if "envio_id" in ok.columns else 0
        saiu = int(ok["email"].astype(str).str.lower().isin(sair).sum()) if "email" in ok.columns else 0
        linhas.append({"Modelo": modelo, "Enviados": len(ok), "Erros": int((grupo["status"] == "erro").sum()),
                       "Clicaram (pessoas)": clicaram,
                       "Taxa de clique": f"{round(100 * clicaram / len(ok), 1)}%" if len(ok) else "—",
                       "Descadastros": saiu})
    return pd.DataFrame(linhas, columns=colunas).sort_values("Enviados", ascending=False).reset_index(drop=True)
