"""Quem clicou no e-mail -> link de WhatsApp com a mensagem pronta (sem Streamlit; testável).

O telefone vem de (1) campanhas enviadas pela FILA (o telefone da planilha fica guardado em `campanha_destinos.dados`) ou
(2) da planilha original, que você pode anexar na tela para cruzar com campanhas antigas. Ligação feita por protocolo + e-mail.
Só PESSOAS entram (cliques de robôs são ignorados), quem pediu para sair nunca recebe link, e telefone fixo não gera link.
"""
import pandas as pd

from core.consulta import buscar_todos
from core.utils import em_lotes
from rotas.processamento import link_whatsapp

from . import metricas
from .colunas import registro_da_linha

MENSAGEM_PADRAO = ("Olá, {cliente}! Aqui é da {empresa}. Identificamos que você abriu o nosso e-mail sobre a retirada do "
                   "equipamento (protocolo {protocolo}). Gostaria de agendar a coleta? Me diga o melhor dia e horário "
                   "para você. Se não quiser receber contato, é só avisar.")
COLUNAS_SAIDA = ["Cliente", "Protocolo", "E-mail", "Telefone", "Modelo", "Clicou em", "WhatsApp"]


def quem_clicou(classificados, envios):
    """DataFrame (um por e-mail) de quem tem ao menos um clique de PESSOA: envio_id, protocolo, nome, email, modelo, clicou_em."""
    vazio = pd.DataFrame(columns=["envio_id", "protocolo", "nome", "email", "modelo", "clicou_em"])
    if classificados is None or classificados.empty or "envio_id" not in classificados.columns:
        return vazio
    pessoas = classificados[classificados["perfil"] == "Pessoa"].copy()
    if pessoas.empty or envios is None or envios.empty:
        return vazio
    col_t = metricas._primeira_coluna(pessoas, metricas.COLUNAS_TEMPO)
    pessoas["_t"] = pd.to_datetime(pessoas[col_t], utc=True, errors="coerce") if col_t else pd.NaT
    primeiro = pessoas.groupby("envio_id", as_index=False)["_t"].min().rename(columns={"_t": "clicou_em"})
    base = envios[envios["status"] == "enviado"].drop_duplicates("envio_id")
    for c in ("protocolo", "nome", "email", "modelo"):
        if c not in base.columns:
            base[c] = ""
    saida = primeiro.merge(base[["envio_id", "protocolo", "nome", "email", "modelo"]], on="envio_id", how="inner")
    return saida.sort_values("clicou_em", ascending=False).reset_index(drop=True)


def _chaves(protocolo, email):
    return f"{protocolo}|{str(email).lower()}", f"{protocolo}|", f"|{str(email).lower()}"


def telefones_da_fila(sb, protocolos):
    """{'protocolo|email': (tel, tel2)} das campanhas enviadas pela fila (onde o telefone da planilha foi guardado)."""
    unicos = sorted({str(p) for p in protocolos if str(p).strip()})
    achados = {}
    for lote in em_lotes(unicos, 150):
        for r in buscar_todos(sb, "campanha_destinos", "id,protocolo,email,dados", {"protocolo": lote}):
            d = r.get("dados") or {}
            if d.get("telefone") or d.get("telefone2"):
                achados[f"{r['protocolo']}|{str(r['email']).lower()}"] = (d.get("telefone", ""), d.get("telefone2", ""))
    return achados


def telefones_da_planilha(df, mapa):
    """Mesma ideia, a partir da planilha original. Também indexa só por protocolo e só por e-mail (se a outra parte mudou)."""
    achados = {}
    for _, linha in df.iterrows():
        reg = registro_da_linha(linha, mapa)
        tels = (reg.get("telefone", ""), reg.get("telefone2", ""))
        if not (tels[0] or tels[1]):
            continue
        completa, so_protocolo, so_email = _chaves(reg["protocolo"], reg["email"])
        achados.setdefault(completa, tels)
        if reg["protocolo"]:
            achados.setdefault(so_protocolo, tels)
        if reg["email"]:
            achados.setdefault(so_email, tels)
    return achados


def montar_tabela(clicaram, fontes, descadastrados, mensagem, empresa):
    """Tabela final com o link do WhatsApp. `fontes`: lista de dicionários de telefone (a primeira que achar vale).
    Devolve (tabela, resumo) com resumo = {'clicaram', 'com_whatsapp', 'sem_telefone', 'descadastrados'}."""
    sair = {str(e).lower() for e in descadastrados}
    linhas, resumo = [], {"clicaram": len(clicaram), "com_whatsapp": 0, "sem_telefone": 0, "descadastrados": 0}
    for r in clicaram.itertuples():
        email = str(r.email).lower()
        if email in sair:
            resumo["descadastrados"] += 1
            continue
        tels = next((f[k] for f in fontes for k in _chaves(r.protocolo, email) if k in f), ("", ""))
        texto = (mensagem.replace("{protocolo}", str(r.protocolo)).replace("{empresa}", str(empresa)))
        link = link_whatsapp(tels[0], tels[1], r.nome, "", texto)
        if link:
            resumo["com_whatsapp"] += 1
        else:
            resumo["sem_telefone"] += 1
        quando = r.clicou_em.tz_convert("America/Sao_Paulo").strftime("%d/%m %H:%M") if pd.notna(r.clicou_em) else ""
        linhas.append({"Cliente": r.nome or "", "Protocolo": r.protocolo, "E-mail": email,
                       "Telefone": tels[0] or tels[1], "Modelo": r.modelo, "Clicou em": quando, "WhatsApp": link})
    return pd.DataFrame(linhas, columns=COLUNAS_SAIDA), resumo
