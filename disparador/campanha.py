"""Loop de disparo, sem Streamlit: recebe funções de apoio (progresso, parar, registrar) e é totalmente testável."""
import random
import time
import uuid
from dataclasses import dataclass, field

from core.utils import agora_br

from .colunas import registro_da_linha
from .envio_smtp import conta_esgotada, escolher_conta
from .planilha import Triagem
from .templates import construir_mensagem, preparar_dados

MAX_ERROS_SEGUIDOS = 5
LIMITE_MAXIMO_POR_CONTA = 500  # teto do Gmail comum; contas novas devem usar bem menos


@dataclass
class Parametros:
    modelo: dict
    nome_modelo: str
    ctx: dict
    delay_min: float = 4
    delay_max: float = 8
    permitir_reenvio: bool = False


@dataclass
class Resumo:
    total: int = 0
    sucessos: int = 0
    erros: int = 0
    ignorados: int = 0
    falhas_log: int = 0
    motivo_parada: str = ""
    resultado: dict = field(default_factory=dict)  # posição -> (status, hora)
    avisos: list = field(default_factory=list)


def executar_campanha(df, mapa, contas, enviados_hoje, descadastrados, ja_enviados, gerente, params,
                      registrar, progresso=None, parar=lambda: False,
                      dormir=time.sleep, sortear=random.uniform):
    """registrar(envio_id, dados, conta_email, modelo, status, erro) -> bool (False = não gravou no histórico).
    progresso(posicao_concluida, resumo) é chamado a cada linha. Devolve Resumo."""
    resumo = Resumo(total=len(df))
    triagem = Triagem(descadastrados, ja_enviados, params.permitir_reenvio)
    d_min, d_max = sorted((params.delay_min, params.delay_max))
    erros_seguidos, ponteiro = 0, 0

    for pos, (_, linha) in enumerate(df.iterrows()):
        if parar():
            resumo.motivo_parada = f"Disparo interrompido no registro {pos}/{resumo.total}."
            break

        envio_id = str(uuid.uuid4())
        reg = registro_da_linha(linha, mapa)
        hora = agora_br().strftime("%d/%m/%Y %H:%M:%S")

        motivo = triagem.motivo(reg["protocolo"], reg["email"])
        if motivo:
            resumo.ignorados += 1
            resumo.resultado[pos] = (motivo, hora)
            if progresso:
                progresso(pos + 1, resumo)
            continue

        conta, ponteiro = escolher_conta(contas, enviados_hoje, ponteiro)
        if conta is None:
            resumo.motivo_parada = ("Limite diário atingido em todas as contas. Continue amanhã com a mesma "
                                    "planilha (quem já recebeu será pulado automaticamente).")
            break

        dados = preparar_dados(reg, params.modelo, params.ctx, envio_id)
        try:
            gerente.enviar(conta, construir_mensagem(conta, dados["email"], dados, params.ctx["empresa"]))
            resumo.sucessos += 1
            erros_seguidos = 0
            enviados_hoje[conta["email"]] = enviados_hoje.get(conta["email"], 0) + 1
            resumo.resultado[pos] = (f"Sucesso (via {conta['email']})", hora)
            if not registrar(envio_id, dados, conta["email"], params.nome_modelo, "enviado", ""):
                resumo.falhas_log += 1
        except Exception as erro:  # noqa: BLE001 — qualquer falha de envio vira registro, não derruba a campanha
            resumo.erros += 1
            erros_seguidos += 1
            resumo.resultado[pos] = (f"Erro: {erro}", hora)
            if not registrar(envio_id, dados, conta["email"], params.nome_modelo, "erro", str(erro)):
                resumo.falhas_log += 1
            if conta_esgotada(erro):
                enviados_hoje[conta["email"]] = 10 ** 9
                gerente.fechar_uma(conta["email"])
                resumo.avisos.append(f"Conta {conta['email']} bloqueada/limite atingido — removida desta campanha.")
            if erros_seguidos >= MAX_ERROS_SEGUIDOS:
                resumo.motivo_parada = (f"{MAX_ERROS_SEGUIDOS} erros seguidos: campanha abortada "
                                        "para proteger as contas.")
                if progresso:
                    progresso(pos + 1, resumo)
                break

        if progresso:
            progresso(pos + 1, resumo)
        dormir(sortear(d_min, d_max))
    return resumo
