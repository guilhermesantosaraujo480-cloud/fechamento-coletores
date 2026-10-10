"""Trilha de auditoria: quem fez o quê. Falhar aqui nunca pode derrubar a ação principal."""
from .utils import agora_br


def registrar(sb, usuario, acao, detalhe=""):
    """Grava em `auditoria` (rode migracao_v2.sql). Devolve True/False sem levantar erro."""
    try:
        sb.table("auditoria").insert({
            "usuario": str(usuario or ""), "acao": str(acao)[:60], "detalhe": str(detalhe)[:500],
            "data_hora": agora_br().isoformat(),
        }).execute()
        return True
    except Exception:
        return False


def listar(sb, limite=300):
    return (sb.table("auditoria").select("*").order("data_hora", desc=True)
              .limit(limite).execute().data) or []
