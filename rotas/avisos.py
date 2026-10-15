"""Avisos por OS (prioridade, agenda, área de risco, tentativas...). Só informam: NADA é excluído da rota.

Motivo: as plataformas reabrem OS 'entregues na loja' ou 'mudou-se', então o sistema marca e deixa a decisão com você.
"""
from datetime import timedelta

import pandas as pd

from .processamento import chave_texto

DIAS_FILA_ALERTA = 30
MOTIVOS_QUE_PEDEM_ATENCAO = (
    "MUDOU", "ENTREGUE NA LOJA", "RETIRADO POR TERCEIROS", "JA COLETADO", "CANCELADA", "DESCARTADO", "CONTINUA ATIVO",
    "RECUSA", "ENDERECO INSUFICIENTE", "ENDERECO INCORRETO", "REGIAO NAO ATENDIDA",
)


def _fmt(d):
    return d.strftime("%d/%m")


def avisos_da_linha(r, data_rota):
    """(lista de textos, urgente?)"""
    textos, urgente = [], False
    if "EXTREMA" in chave_texto(r.get("prioridade", "")):
        textos.append("🔴 Prioridade máxima")
        urgente = True
    d = r.get("agenda_dt")
    if d is not None and not pd.isna(d):
        if d == data_rota:
            textos.append("📅 Agendada para HOJE")
            urgente = True
        elif d == data_rota + timedelta(days=1):
            textos.append(f"📅 Agendada para amanhã ({_fmt(d)})")
        elif data_rota - timedelta(days=5) <= d < data_rota:
            textos.append(f"📅 Agenda vencida ({_fmt(d)})")
            urgente = True
        # datas longe no futuro (ex.: 30/10 padrão do sistema) não viram aviso
    if "RISCO" in chave_texto(r.get("ocorrencia", "")):
        textos.append("⚠️ Área de risco")
    n = int(r.get("tentativas_n", 0) or 0)
    motivo = str(r.get("motivo", "") or "").strip()
    km = chave_texto(motivo)
    if n >= 2:
        textos.append(f"🔁 {n} agendamentos")
    if motivo:
        if "AUSENTE" in km:
            textos.append("🚪 Já tentada: cliente ausente")
        elif any(k in km for k in MOTIVOS_QUE_PEDEM_ATENCAO):
            textos.append(f"ℹ️ Último motivo: {motivo}")
    if str(r.get("reaberta", "") or "").strip():
        textos.append("↩️ Reaberta")
    dias = int(r.get("backlog_n", 0) or 0)
    if dias >= DIAS_FILA_ALERTA:
        textos.append(f"⏳ {dias} dias na fila")
    return textos, urgente


def aplicar_avisos(can, data_rota):
    """Devolve cópia com as colunas `avisos` (texto) e `urgente` (bool)."""
    saida = can.copy()
    linhas = [avisos_da_linha(r, data_rota) for r in can.to_dict("records")]
    saida["avisos"] = [" · ".join(t) for t, _ in linhas]
    saida["urgente"] = [u for _, u in linhas]
    return saida


def contagem(can):
    """Resumo para a mensagem do WhatsApp e para os cartões da tela."""
    av = can["avisos"] if "avisos" in can else pd.Series("", index=can.index)
    return {
        "prioridade": int(av.str.contains("Prioridade máxima", regex=False).sum()),
        "hoje": int(av.str.contains("HOJE", regex=False).sum()),
        "vencidas": int(av.str.contains("Agenda vencida", regex=False).sum()),
        "risco": int(av.str.contains("Área de risco", regex=False).sum()),
        "repetidas": int(av.str.contains("agendamentos", regex=False).sum()),
        "ausentes": int(av.str.contains("cliente ausente", regex=False).sum()),
        "reabertas": int(av.str.contains("Reaberta", regex=False).sum()),
        "fila_longa": int(av.str.contains("dias na fila", regex=False).sum()),
        "com_aviso": int((av != "").sum()),
    }


def linha_resumo(c):
    partes = []
    if c["prioridade"]:
        partes.append(f"🔴 {c['prioridade']} prioridade máxima")
    if c["hoje"]:
        partes.append(f"📅 {c['hoje']} agendada(s) p/ hoje")
    if c["vencidas"]:
        partes.append(f"⏰ {c['vencidas']} agenda(s) vencida(s)")
    if c["risco"]:
        partes.append(f"⚠️ {c['risco']} área de risco")
    return " · ".join(partes)
