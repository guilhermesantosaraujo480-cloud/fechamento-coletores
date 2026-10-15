"""Fila de campanhas de e-mail (banco). Sem Streamlit: usado pela tela E pelo trabalhador agendado."""
from datetime import datetime, timedelta, timezone

from core.consulta import buscar_todos

LOTE_INSERCAO = 500
STATUS_ATIVOS = ("pendente", "rodando")
ROTULO = {"pendente": "⏳ Na fila", "rodando": "🟢 Enviando", "pausada": "⏸️ Pausada", "concluida": "✅ Concluída",
          "cancelada": "🛑 Cancelada"}


def _completar(c):
    """Garante os contadores (o banco já traz 0 por padrão; isto só protege contra linhas antigas/parciais)."""
    if c:
        for k in ("total", "enviados", "erros", "ignorados", "falhas_log"):
            c[k] = int(c.get(k) or 0)
    return c


def agora_iso():
    return datetime.now(timezone.utc).isoformat()


def _em(segundos):
    return (datetime.now(timezone.utc) + timedelta(seconds=segundos)).isoformat()


# ----------------------------------------------------------------------------- criar
def criar_campanha(sb, usuario, nome, modelo_nome, modelo, ctx, delay_min, delay_max, permitir_reenvio, registros):
    """registros: lista de dicts (colunas.registro_da_linha). Repetidos na mesma planilha entram já como 'ignorado'."""
    camp = sb.table("campanhas").insert({
        "nome": nome.strip() or modelo_nome, "status": "pendente", "criado_por": usuario, "modelo_nome": modelo_nome,
        "modelo": modelo, "ctx": ctx, "delay_min": float(delay_min), "delay_max": float(delay_max),
        "permitir_reenvio": bool(permitir_reenvio), "total": len(registros), "atualizado_em": agora_iso(),
    }).execute().data[0]
    _completar(camp)
    vistos, linhas = set(), []
    for ordem, reg in enumerate(registros):
        chave = f"{reg.get('protocolo', '')}|{reg.get('email', '')}"
        repetido = chave in vistos
        vistos.add(chave)
        linhas.append({"campanha_id": camp["id"], "ordem": ordem, "protocolo": reg.get("protocolo", ""),
                       "email": reg.get("email", ""), "dados": reg,
                       "status": "ignorado" if repetido else "pendente",
                       "detalhe": "IGNORADO: duplicado na planilha" if repetido else ""})
    for i in range(0, len(linhas), LOTE_INSERCAO):
        sb.table("campanha_destinos").insert(linhas[i:i + LOTE_INSERCAO]).execute()
    ign = sum(1 for x in linhas if x["status"] == "ignorado")
    if ign:
        sb.table("campanhas").update({"ignorados": ign}).eq("id", camp["id"]).execute()
        camp["ignorados"] = ign
    return camp


# --------------------------------------------------------------------------- consultar
def listar(sb, limite=30):
    return [_completar(c) for c in sb.table("campanhas").select("*").order("id", desc=True).limit(limite).execute().data or []]


def obter(sb, camp_id):
    r = sb.table("campanhas").select("*").eq("id", camp_id).limit(1).execute().data
    return _completar(r[0]) if r else None


def pendentes_na_campanha(sb, camp_id):
    return len(sb.table("campanha_destinos").select("id").eq("campanha_id", camp_id).eq("status", "pendente").execute().data or [])


def destinos(sb, camp_id, status=None):
    filtros = {"campanha_id": camp_id}
    if status:
        filtros["status"] = status
    return buscar_todos(sb, "campanha_destinos", "ordem,protocolo,email,status,detalhe,processado_em,dados", filtros, ordem="id")


def contagens(sb, camp_id):
    """Conta de verdade no banco (corrige qualquer diferença dos contadores)."""
    cont = {"pendente": 0, "enviando": 0, "enviado": 0, "erro": 0, "ignorado": 0}
    for r in buscar_todos(sb, "campanha_destinos", "id,status", {"campanha_id": camp_id}, ordem="id"):
        cont[r["status"]] = cont.get(r["status"], 0) + 1
    return cont


def tempo_restante_min(camp, pendentes):
    """Estimativa só de intervalo entre e-mails (o limite diário das contas pode adiar o resto para outro dia)."""
    media = (float(camp.get("delay_min") or 4) + float(camp.get("delay_max") or 8)) / 2 + 1.5
    return round(pendentes * media / 60, 1)


# -------------------------------------------------------------------------- controlar
def definir_status(sb, camp_id, status, motivo=None, so_se=None):
    """so_se: tupla de status permitidos como origem (evita sobrescrever uma pausa/cancelamento feito na tela)."""
    q = sb.table("campanhas").update({"status": status, "motivo": motivo, "atualizado_em": agora_iso(),
                                      **({"finalizado_em": agora_iso()} if status in ("concluida", "cancelada") else {})})
    q = q.eq("id", camp_id)
    if so_se:
        q = q.in_("status", list(so_se))
    return q.execute().data


def pausar(sb, camp_id):
    definir_status(sb, camp_id, "pausada", "Pausada por você.", so_se=STATUS_ATIVOS)


def retomar(sb, camp_id):
    sb.table("campanhas").update({"status": "pendente", "motivo": None, "lease_ate": None, "atualizado_em": agora_iso()}) \
        .eq("id", camp_id).in_("status", ["pausada", "concluida"]).execute()


def cancelar(sb, camp_id):
    definir_status(sb, camp_id, "cancelada", "Cancelada por você.", so_se=STATUS_ATIVOS + ("pausada",))


def recolocar_erros(sb, camp_id):
    """Os que deram erro voltam para a fila (ex.: depois de arrumar a conta). Devolve quantos."""
    linhas = sb.table("campanha_destinos").update({"status": "pendente", "detalhe": ""}) \
        .eq("campanha_id", camp_id).eq("status", "erro").execute().data or []
    if linhas:
        retomar(sb, camp_id)
    return len(linhas)


# ------------------------------------------------------------------------- trabalhador
def candidatas(sb):
    """Campanhas que o trabalhador deve olhar agora (na ordem de criação)."""
    return sb.table("campanhas").select("*").in_("status", list(STATUS_ATIVOS)).order("id").execute().data or []


def reservar(sb, camp, segundos=180):
    """Pega a 'reserva' da campanha. False se outro trabalhador está com ela ou se a tela pausou/cancelou."""
    atual = obter(sb, camp["id"])
    if not atual or atual["status"] not in STATUS_ATIVOS:
        return False
    if atual.get("lease_ate") and str(atual["lease_ate"]) > agora_iso():
        return False
    campos = {"status": "rodando", "lease_ate": _em(segundos), "atualizado_em": agora_iso()}
    if not atual.get("iniciado_em"):
        campos["iniciado_em"] = agora_iso()
    ok = sb.table("campanhas").update(campos).eq("id", camp["id"]).eq("status", atual["status"]).execute().data
    return bool(ok)


def renovar(sb, camp_id, contadores, segundos=180):
    sb.table("campanhas").update({**contadores, "lease_ate": _em(segundos), "atualizado_em": agora_iso()}) \
        .eq("id", camp_id).execute()


def liberar(sb, camp_id, status, motivo=None, contadores=None):
    """Solta a reserva e define o status final DESTA rodada, sem pisar numa pausa/cancelamento da tela."""
    campos = {"status": status, "motivo": motivo, "lease_ate": None, "atualizado_em": agora_iso(), **(contadores or {})}
    if status == "concluida":
        campos["finalizado_em"] = agora_iso()
    sb.table("campanhas").update(campos).eq("id", camp_id).eq("status", "rodando").execute()
    # se a tela mudou o status no meio (pausada/cancelada), só solta a reserva:
    sb.table("campanhas").update({"lease_ate": None, **(contadores or {})}).eq("id", camp_id).execute()


def proximos(sb, camp_id, quantos):
    return sb.table("campanha_destinos").select("*").eq("campanha_id", camp_id).eq("status", "pendente") \
        .order("ordem").limit(quantos).execute().data or []


def marcar(sb, ids, status, detalhe=""):
    if ids:
        sb.table("campanha_destinos").update({"status": status, "detalhe": detalhe}).in_("id", list(ids)).execute()


def concluir_destino(sb, destino_id, status, detalhe):
    sb.table("campanha_destinos").update({"status": status, "detalhe": str(detalhe)[:300], "processado_em": agora_iso()}) \
        .eq("id", destino_id).execute()


def em_andamento(sb, camp_id):
    """Destinos que ficaram 'enviando' (o trabalhador caiu no meio)."""
    return sb.table("campanha_destinos").select("*").eq("campanha_id", camp_id).eq("status", "enviando").execute().data or []
