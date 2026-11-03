"""Tolerância a falhas passageiras de rede (sem Streamlit; testável).

`com_tentativas` repete uma operação que PODE ser repetida sem efeito colateral (leituras e envio de arquivo com o mesmo nome),
esperando um pouco mais a cada tentativa. Escritas no banco NÃO são repetidas aqui (poderiam duplicar): elas usam chave de idempotência.
"""
import time

_PEDACOS_TRANSITORIOS = ("timeout", "connect", "network", "transport", "remoteprotocol", "readerror", "writeerror",
                         "pool", "disconnected", "connectionerror", "brokenpipe", "reset")


def eh_transitorio(erro):
    """True para falhas típicas de rede (queda, tempo esgotado, conexão reaproveitada que o servidor fechou)."""
    if isinstance(erro, (ConnectionError, TimeoutError)):
        return True
    for classe in type(erro).__mro__:
        nome = classe.__name__.lower()
        if any(p in nome for p in _PEDACOS_TRANSITORIOS):
            return True
    texto = str(erro).lower()
    return "server disconnected" in texto or "connection reset" in texto or "temporarily unavailable" in texto


def com_tentativas(operacao, tentativas=3, espera=0.4, dormir=time.sleep):
    """Executa `operacao()`; se falhar por rede, tenta de novo (até `tentativas` vezes). Outros erros sobem na hora."""
    ultimo = None
    for n in range(tentativas):
        try:
            return operacao()
        except Exception as erro:  # noqa: BLE001
            if not eh_transitorio(erro) or n == tentativas - 1:
                raise
            ultimo = erro
            dormir(espera * (n + 1))
    raise ultimo  # nunca chega aqui; por garantia
