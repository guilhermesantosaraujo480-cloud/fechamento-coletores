"""Fila de lotes de bipagem (banco). Sem Streamlit nem navegador: usada pela tela E pelo agente local."""
from datetime import datetime, timedelta, timezone

STATUS_ATIVOS = ("pendente", "executando", "parando")
ROTULO = {"pendente": "⏳ Na fila", "executando": "🟢 Executando", "parando": "🛑 Parando…", "parado": "⏸️ Parado",
          "concluido": "✅ Concluído", "erro": "❌ Parou por erro", "cancelado": "🚫 Cancelado"}
AGENTE_PADRAO = "principal"


def agora_iso():
    return datetime.now(timezone.utc).isoformat()


def _completar(l):
    if l:
        for k in ("qtd_aparelhos", "limite_ordens", "indice_pool", "ordens_ok", "ordens_erro"):
            l[k] = int(l.get(k) or 0)
        l["seriais"] = list(l.get("seriais") or [])
    return l


# ----------------------------------------------------------------------------- tela
def criar_lote(sb, usuario, nome, seriais, qtd_aparelhos, equip1, equip2, limite_ordens):
    seriais = [str(s).strip() for s in seriais if str(s).strip()]
    if not seriais:
        raise ValueError("Nenhum serial para bipar.")
    if int(qtd_aparelhos) not in (1, 2):
        raise ValueError("Aparelhos por OS: 1 ou 2.")
    if int(limite_ordens) < 1:
        raise ValueError("Informe quantas ordens bipar.")
    linha = sb.table("bipagem_lotes").insert({
        "nome": (nome or "").strip() or "Lote de bipagem", "status": "pendente", "criado_por": usuario,
        "seriais": seriais, "qtd_aparelhos": int(qtd_aparelhos), "equip1": equip1,
        "equip2": equip2 if int(qtd_aparelhos) == 2 else None, "limite_ordens": int(limite_ordens),
        "indice_pool": 0, "ordens_ok": 0, "ordens_erro": 0, "parar": False, "mensagem": "",
    }).execute().data[0]
    return _completar(linha)


def listar_lotes(sb, limite=20):
    # `seriais` pode ser grande: a lista da tela não precisa dele
    colunas = ("id,criado_em,criado_por,nome,status,qtd_aparelhos,equip1,equip2,limite_ordens,indice_pool,"
               "ordens_ok,ordens_erro,mensagem,parar,iniciado_em,finalizado_em,agente")
    linhas = sb.table("bipagem_lotes").select(colunas).order("id", desc=True).limit(limite).execute().data or []
    return [_completar(l) for l in linhas]


def obter_lote(sb, lote_id):
    linhas = sb.table("bipagem_lotes").select("*").eq("id", lote_id).execute().data or []
    return _completar(linhas[0]) if linhas else None


def itens(sb, lote_id):
    return sb.table("bipagem_itens").select("*").eq("lote_id", lote_id).order("id").execute().data or []


def pedir_parada(sb, lote_id):
    """Pendente vira cancelado na hora; em execução o agente para ao terminar a OS atual (nunca no meio de uma)."""
    lote = obter_lote(sb, lote_id)
    if not lote:
        return
    if lote["status"] == "pendente":
        sb.table("bipagem_lotes").update({"status": "cancelado", "parar": True, "finalizado_em": agora_iso(),
                                          "mensagem": "Cancelado antes de começar."}).eq("id", lote_id).execute()
    elif lote["status"] == "executando":
        sb.table("bipagem_lotes").update({"status": "parando", "parar": True}).eq("id", lote_id).execute()


def retomar(sb, lote_id):
    """Volta para a fila um lote parado/interrompido; continua de onde parou (a lista da plataforma já não tem as OS feitas)."""
    sb.table("bipagem_lotes").update({"status": "pendente", "parar": False, "mensagem": "",
                                      "finalizado_em": None}).eq("id", lote_id).execute()


# ---------------------------------------------------------------------------- agente
def proximo_lote(sb):
    """Lote para o agente trabalhar: primeiro o que ficou em execução (retomada), depois o mais antigo da fila."""
    for status in ("executando", "pendente"):
        linhas = (sb.table("bipagem_lotes").select("*").eq("status", status).order("id").limit(1).execute().data or [])
        if linhas:
            return _completar(linhas[0])
    return None


def iniciar(sb, lote, agente):
    sb.table("bipagem_lotes").update({
        "status": "executando", "parar": False, "agente": agente, "mensagem": "",
        "iniciado_em": lote.get("iniciado_em") or agora_iso(),
    }).eq("id", lote["id"]).execute()


def progresso(sb, lote_id, **campos):
    sb.table("bipagem_lotes").update(campos).eq("id", lote_id).execute()


def finalizar(sb, lote_id, status, mensagem=""):
    sb.table("bipagem_lotes").update({"status": status, "mensagem": mensagem[:500], "parar": False,
                                      "finalizado_em": agora_iso()}).eq("id", lote_id).execute()


def deve_parar(sb, lote_id):
    lote = obter_lote(sb, lote_id)
    return bool(lote) and (bool(lote.get("parar")) or lote["status"] in ("parando", "cancelado"))


def registrar_item(sb, lote_id, os_, status, serial1="", serial2="", tentativas=0, obs=""):
    sb.table("bipagem_itens").insert({
        "lote_id": lote_id, "os": os_, "status": status, "serial1": serial1 or "", "serial2": serial2 or "",
        "tentativas": int(tentativas), "obs": (obs or "")[:500], "criado_em": agora_iso(),
    }).execute()


def sinal(sb, nome=AGENTE_PADRAO, info=""):
    """Batimento do agente: a tela mostra se ele está ligado."""
    sb.table("bipagem_agente").upsert({"nome": nome, "ultimo_sinal": agora_iso(), "info": info[:200]},
                                      on_conflict="nome").execute()


def agente_online(sb, nome=AGENTE_PADRAO, tolerancia=90):
    """(online?, info, ultimo_sinal)"""
    linhas = sb.table("bipagem_agente").select("*").eq("nome", nome).execute().data or []
    if not linhas:
        return False, "", None
    ultimo = linhas[0].get("ultimo_sinal")
    try:
        quando = datetime.fromisoformat(str(ultimo).replace("Z", "+00:00"))
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
        online = datetime.now(timezone.utc) - quando <= timedelta(seconds=tolerancia)
    except ValueError:
        online = False
    return online, linhas[0].get("info") or "", ultimo
