"""Registro da coleta enviada pelo coletor, à prova de repetição depois de queda de internet (sem Streamlit; testável)."""
from .resiliencia import com_tentativas


def registrar_coleta(sb, linha, chave):
    """Grava a coleta com uma `chave_envio` única por tentativa de envio.

    Se a gravação deu erro DEPOIS de chegar ao banco (queda de internet na resposta), a conferência pela chave descobre que a coleta existe e
    não dá erro; se o coletor tocar em Enviar de novo, o índice único do banco impede a segunda coleta. Devolve True se a coleta existe."""
    try:
        sb.table("coletas").insert({**linha, "chave_envio": chave}).execute()
        return True
    except Exception:  # noqa: BLE001
        try:
            achou = com_tentativas(sb.table("coletas").select("id").eq("chave_envio", chave).limit(1).execute).data
        except Exception:  # noqa: BLE001 — sem como conferir: devolve o erro original
            raise
        if achou:
            return True
        raise
