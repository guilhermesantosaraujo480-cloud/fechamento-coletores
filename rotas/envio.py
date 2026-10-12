"""Loop de envio das rotas (sem Streamlit; sleep e registro são injetados, então é testável)."""
import random
import time
from dataclasses import dataclass

from .whatsapp import ErroWhats

MAX_ERROS_SEGUIDOS = 3


@dataclass
class Resultado:
    coletor: str
    destino: str
    status: str   # "enviado" | "erro"
    detalhe: str = ""


def enviar_rotas(gateway, pacotes, destinos, registrar, individual=False,
                 dormir=time.sleep, sortear=random.uniform, pausa=(3, 6)):
    """pacotes: [{coletor, qtd, conteudo (bytes xlsx), arquivo, mensagem, telefone}].
    destinos: grupos (ou números) que recebem TODAS as rotas. individual: manda também para o telefone do coletor.
    O arquivo vai com a mensagem na legenda (uma mensagem só por destino). registrar(resultado, pacote)."""
    resultados, erros_seguidos = [], 0
    for pacote in pacotes:
        alvos = list(destinos)
        if individual and pacote.get("telefone"):
            alvos.append(pacote["telefone"])
        for alvo in alvos:
            try:
                gateway.enviar_arquivo(alvo, pacote["conteudo"], pacote["arquivo"], pacote["mensagem"])
                res, erros_seguidos = Resultado(pacote["coletor"], alvo, "enviado"), 0
            except ErroWhats as erro:
                res, erros_seguidos = Resultado(pacote["coletor"], alvo, "erro", str(erro)), erros_seguidos + 1
            resultados.append(res)
            registrar(res, pacote)
            if erros_seguidos >= MAX_ERROS_SEGUIDOS:
                return resultados, f"{MAX_ERROS_SEGUIDOS} erros seguidos: envio interrompido. Confira a conexão do WhatsApp."
            dormir(sortear(*pausa))
    return resultados, ""
