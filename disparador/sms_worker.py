"""Trabalhador do SMS em segundo plano. Roda no GitHub Actions (ver .github/workflows/sms.yml):

    python -m disparador.sms_worker

Lê a fila `sms_campanhas`, entrega cada SMS ao app do celular (SMS Gateway for Android) respeitando: intervalo aleatório entre
mensagens, limite diário de cada celular, horário permitido (e domingo), lista de "SAIR" e quem já recebeu. O que não saiu volta
para a fila; pode ser interrompido a qualquer momento. Variáveis: SUPABASE_URL, SUPABASE_KEY (service_role), CHAVE_CRIPTO, MAX_MINUTOS.
"""
import os
import random
import sys
import time

from core.utils import agora_br

from . import gatilho, sms
from . import repositorio as repo
from . import sms_banco as banco
from . import sms_gateway
from .crypto import Cofre

LOTE = 10
MAX_ERROS_SEGUIDOS = 5


def fora_do_horario(camp, agora):
    """'' se pode enviar agora; senão o motivo (mostrado na tela)."""
    if agora.weekday() == 6 and not camp.get("domingo"):
        return "Domingo: o envio continua na segunda-feira (você pode liberar o domingo na campanha)."
    ini, fim = camp.get("janela_ini"), camp.get("janela_fim")
    if ini is not None and fim is not None and not sms.limitar_janela(agora, float(ini), float(fim)):
        return f"Fora do horário permitido ({int(ini)}h às {int(fim)}h): continua automaticamente quando abrir."
    return ""


def recuperar_interrompidos(sb, camp_id, ja_enviados):
    """Linhas que ficaram 'enviando' porque o trabalhador caiu: se já constam como enviadas, fecha; senão volta à fila."""
    for d in banco.em_andamento(sb, camp_id):
        chave = f"{d['protocolo']}|{sms.normalizar_bloqueio(d['telefone'])}"
        if chave in ja_enviados:
            banco.concluir_destino(sb, d["id"], "enviado", "Confirmado pelo histórico após interrupção.")
        else:
            banco.marcar(sb, [d["id"]], "pendente")


def _escolher(gateways, usados, ponteiro):
    """Próximo celular com limite sobrando (rodízio). (gateway ou None, novo ponteiro)."""
    n = len(gateways)
    for i in range(n):
        g = gateways[(ponteiro + i) % n]
        if usados.get(g["id"], 0) < int(g.get("limite_diario") or 0):
            return g, (ponteiro + i + 1) % n
    return None, ponteiro


def processar_campanha(sb, camp, cofre, prazo, abrir=None, relogio=time.monotonic, dormir=time.sleep, sortear=None,
                       agora=agora_br, lote=LOTE):
    """Devolve o motivo da saída: 'concluida' | 'pausada' | 'cancelada' | 'tempo' | 'limite' | 'horario' | 'ocupada' | 'sem_celular'."""
    sortear = sortear or random.uniform
    if not banco.reservar(sb, camp):
        return "ocupada"
    camp = banco.obter(sb, camp["id"])
    contadores = {k: int(camp.get(k) or 0) for k in ("enviados", "erros", "ignorados")}
    textos = camp.get("textos") or []
    ctx = camp.get("ctx") or {}
    d_min, d_max = sorted((float(camp.get("delay_min") or 20), float(camp.get("delay_max") or 45)))
    permitir = bool(camp.get("permitir_reenvio"))
    sem_acentos = bool(camp.get("sem_acentos", True))
    apps = {}  # id do celular -> cliente da API (criado uma vez por rodada)
    ruins = set()  # celulares com usuário/senha recusados nesta rodada
    ponteiro, erros_seguidos = 0, 0
    try:
        if not textos:
            banco.liberar(sb, camp["id"], "pausada", "A campanha não tem texto.", contadores)
            return "pausada"
        ja = banco.ja_enviados(sb, banco.protocolos(sb, camp["id"]))
        recuperar_interrompidos(sb, camp["id"], ja)
        while True:
            if relogio() >= prazo:
                banco.liberar(sb, camp["id"], "pendente", "Continua no próximo ciclo.", contadores)
                return "tempo"
            motivo_horario = fora_do_horario(camp, agora())
            if motivo_horario:
                banco.liberar(sb, camp["id"], "pendente", motivo_horario, contadores)
                return "horario"
            pendentes = banco.proximos(sb, camp["id"], lote)
            if not pendentes:
                cont = banco.contagens(sb, camp["id"])
                contadores.update(enviados=cont["enviado"], erros=cont["erro"], ignorados=cont["ignorado"])
                banco.liberar(sb, camp["id"], "concluida", None, contadores)
                return "concluida"
            gateways, sem_senha = banco.carregar_gateways_ativos(sb, cofre)
            gateways = [g for g in gateways if g["id"] not in ruins]
            if not gateways:
                dica = " (senha ilegível: confira a CHAVE_CRIPTO)" if sem_senha else ""
                banco.liberar(sb, camp["id"], "pausada",
                              "Nenhum celular de SMS ativo e com acesso válido" + dica + ". Confira em 📱 SMS → Celulares.", contadores)
                return "sem_celular"
            usados = banco.enviados_hoje(sb)
            bloqueados = banco.telefones_descadastrados(sb)
            emails_sair = repo.emails_descadastrados(sb)
            banco.marcar(sb, [d["id"] for d in pendentes], "enviando")
            for pos, d in enumerate(pendentes):
                atual = banco.obter(sb, camp["id"])
                if relogio() >= prazo or not atual or atual["status"] != "rodando":
                    banco.marcar(sb, [x["id"] for x in pendentes[pos:]], "pendente")
                    if atual and atual["status"] in ("pausada", "cancelada"):
                        banco.liberar(sb, camp["id"], atual["status"], atual.get("motivo"), contadores)
                        return atual["status"]
                    banco.liberar(sb, camp["id"], "pendente", "Continua no próximo ciclo.", contadores)
                    return "tempo"
                motivo_horario = fora_do_horario(camp, agora())
                if motivo_horario:  # a janela pode fechar no meio do lote
                    banco.marcar(sb, [x["id"] for x in pendentes[pos:]], "pendente")
                    banco.liberar(sb, camp["id"], "pendente", motivo_horario, contadores)
                    return "horario"
                motivo = sms.triar(d.get("telefone", ""), bloqueados, ja, permitir, d.get("protocolo", ""), d.get("email", ""), emails_sair)
                if motivo:
                    banco.concluir_destino(sb, d["id"], "ignorado", f"IGNORADO: {motivo}")
                    contadores["ignorados"] += 1
                    banco.renovar(sb, camp["id"], contadores)
                    continue
                gateway, ponteiro = _escolher([g for g in gateways if g["id"] not in ruins], usados, ponteiro)
                if gateway is None:
                    banco.marcar(sb, [x["id"] for x in pendentes[pos:]], "pendente")
                    if ruins and not [g for g in gateways if g["id"] not in ruins]:
                        banco.liberar(sb, camp["id"], "pausada", "O aplicativo recusou o usuário/senha do celular. Confira em "
                                      "📱 SMS → Celulares (use 🔌 Testar conexão) e depois Retomar.", contadores)
                        return "sem_celular"
                    banco.liberar(sb, camp["id"], "pendente", "Limite diário dos celulares atingido: continua amanhã "
                                  "automaticamente.", contadores)
                    return "limite"
                indice = int((d.get("dados") or {}).get("_texto", pos)) % len(textos)
                texto = sms.montar_texto(textos[indice], d, ctx, sem_acentos)
                cliente = apps.get(gateway["id"]) or apps.setdefault(gateway["id"], sms_gateway.criar(gateway, cofre, abrir))
                modelo = f"Texto {indice + 1}"
                try:
                    msg_id, _estado = cliente.enviar(d["telefone"], texto)
                except sms_gateway.ErroGateway as erro:
                    if erro.tipo == "credencial":
                        ruins.add(gateway["id"])
                        banco.marcar(sb, [d["id"]], "pendente")
                        continue
                    if erro.tipo == "numero":
                        banco.registrar_envio(sb, camp["id"], d, texto, modelo, gateway, "erro", str(erro))
                        banco.concluir_destino(sb, d["id"], "erro", f"Erro: {erro}", gateway["id"])
                        contadores["erros"] += 1
                        erros_seguidos += 1
                    else:  # temporário: volta para a fila e espera
                        banco.marcar(sb, [d["id"]], "pendente", f"Tentará de novo: {erro}")
                        erros_seguidos += 1
                        if erro.espera:
                            dormir(min(erro.espera, 120))
                    banco.renovar(sb, camp["id"], contadores)
                    if erros_seguidos >= MAX_ERROS_SEGUIDOS:
                        banco.marcar(sb, [x["id"] for x in pendentes[pos + 1:]], "pendente")
                        banco.liberar(sb, camp["id"], "pausada", f"{MAX_ERROS_SEGUIDOS} erros seguidos (último: {erro}). "
                                      "Confira o celular/app e use Retomar.", contadores)
                        return "pausada"
                    continue
                erros_seguidos = 0
                usados[gateway["id"]] = usados.get(gateway["id"], 0) + 1
                ja.add(f"{d['protocolo']}|{sms.normalizar_bloqueio(d['telefone'])}")
                banco.registrar_envio(sb, camp["id"], d, texto, modelo, gateway, "enviado", "", msg_id)
                banco.concluir_destino(sb, d["id"], "enviado", f"Sucesso (via {gateway['nome']})", gateway["id"], msg_id)
                contadores["enviados"] += 1
                banco.renovar(sb, camp["id"], contadores)
                dormir(sortear(d_min, d_max))
    except Exception as erro:  # noqa: BLE001 — falha inesperada pausa a campanha em vez de repetir em loop
        banco.marcar(sb, [d["id"] for d in banco.em_andamento(sb, camp["id"])], "pendente")
        banco.liberar(sb, camp["id"], "pausada", f"Erro inesperado do trabalhador: {str(erro)[:200]}", contadores)
        raise


def rodar(sb, cofre, minutos=14, abrir=None, relogio=time.monotonic, dormir=time.sleep, sortear=None, agora=agora_br, log=print):
    """Processa as campanhas de SMS em fila até acabar o tempo. Devolve (houve_trabalho, ainda_ha_o_que_fazer)."""
    prazo = relogio() + minutos * 60
    houve, restante = False, False
    for camp in banco.candidatas(sb):
        motivo = processar_campanha(sb, camp, cofre, prazo, abrir, relogio, dormir, sortear, agora)
        log(f"SMS campanha {camp['id']} ({camp['nome']}): {motivo}")
        if motivo in ("concluida", "tempo", "pausada", "cancelada"):
            houve = True
        if motivo == "tempo":
            restante = True
            break
        if motivo in ("limite", "sem_celular"):  # os celulares são compartilhados: nada mais a fazer agora
            break
    return houve, restante


def main(env=None, criar_cliente=None):
    env = env if env is not None else os.environ
    url, chave = env.get("SUPABASE_URL"), env.get("SUPABASE_KEY")
    if not (url and chave):
        print("Faltam SUPABASE_URL e SUPABASE_KEY.", file=sys.stderr)
        return 1
    if criar_cliente is None:
        from supabase import create_client as criar_cliente
    sb = criar_cliente(url, chave)
    cofre = Cofre(env.get("CHAVE_CRIPTO"))
    houve, restante = rodar(sb, cofre, float(env.get("MAX_MINUTOS", 14)))
    if restante and env.get("GITHUB_TOKEN") and env.get("GITHUB_REPOSITORY") and houve:
        try:  # ainda tem SMS na fila e o tempo acabou: chama o próximo ciclo na hora
            gatilho.disparar_workflow(env["GITHUB_REPOSITORY"], env["GITHUB_TOKEN"], gatilho.WORKFLOW_SMS,
                                      env.get("GITHUB_REF_NAME", "main"))
            print("Próximo ciclo acionado.")
        except gatilho.ErroGatilho as erro:
            print(f"Não consegui acionar o próximo ciclo ({erro}); o agendamento cuida disso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
