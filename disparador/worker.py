"""Trabalhador do disparo em segundo plano. Roda no GitHub Actions (ver .github/workflows/disparador.yml):

    python -m disparador.worker

Lê a fila no Supabase, envia por SMTP respeitando intervalo e limite diário de cada conta, e grava o andamento no banco.
Pode ser interrompido a qualquer momento: o que não saiu volta para a fila; o que saiu já está no histórico.
Variáveis de ambiente: SUPABASE_URL, SUPABASE_KEY (use a service_role), CHAVE_CRIPTO, MAX_MINUTOS (padrão 14).
"""
import os
import sys
import time

import pandas as pd

from . import campanha, colunas, fila
from . import repositorio as repo
from . import gatilho
from .crypto import Cofre
from .envio_smtp import GerenteSMTP

LOTE = 25
COLUNAS = list(colunas.CAMPOS)


def _status_do_texto(texto):
    if texto.startswith("Sucesso"):
        return "enviado"
    if texto.startswith("IGNORADO"):
        return "ignorado"
    return "erro"


def recuperar_interrompidos(sb, camp_id, ja_enviados):
    """Linhas que ficaram 'enviando' porque o trabalhador caiu: se já constam como enviadas, fecha; senão volta à fila."""
    for d in fila.em_andamento(sb, camp_id):
        if f"{d['protocolo']}|{d['email']}" in ja_enviados:
            fila.concluir_destino(sb, d["id"], "enviado", "Confirmado pelo histórico após interrupção.")
        else:
            fila.marcar(sb, [d["id"]], "pendente")


def processar_campanha(sb, camp, cofre, gerente, prazo, relogio=time.monotonic, dormir=time.sleep,
                       sortear=None, lote=LOTE):
    """Devolve o motivo da saída: 'concluida' | 'pausada' | 'cancelada' | 'tempo' | 'limite' | 'ocupada' | 'sem_conta'."""
    import random
    sortear = sortear or random.uniform
    if not fila.reservar(sb, camp):
        return "ocupada"
    camp = fila.obter(sb, camp["id"])
    contadores = {k: int(camp.get(k) or 0) for k in ("enviados", "erros", "ignorados", "falhas_log")}
    params = campanha.Parametros(camp["modelo"], camp.get("modelo_nome") or camp["nome"], camp["ctx"],
                                 float(camp["delay_min"]), float(camp["delay_max"]), bool(camp["permitir_reenvio"]))
    try:
        ja_enviados = repo.ja_enviados(sb, fila.protocolos(sb, camp["id"]))
        recuperar_interrompidos(sb, camp["id"], ja_enviados)
        mapa = {c: c for c in COLUNAS}
        while True:
            if relogio() >= prazo:
                fila.liberar(sb, camp["id"], "pendente", "Continua no próximo ciclo.", contadores)
                return "tempo"
            lote_atual = fila.proximos(sb, camp["id"], lote)
            if not lote_atual:
                cont = fila.contagens(sb, camp["id"])
                contadores.update(enviados=cont["enviado"], erros=cont["erro"], ignorados=cont["ignorado"])
                fila.liberar(sb, camp["id"], "concluida", None, contadores)
                return "concluida"
            contas, sem_senha = repo.carregar_contas_ativas(sb, cofre)
            if not contas:
                fila.liberar(sb, camp["id"], "pausada",
                             "Nenhuma conta de e-mail ativa/legível (confira a CHAVE_CRIPTO e a seção Contas).", contadores)
                return "sem_conta"
            enviados_hoje = repo.contar_enviados_hoje(sb)
            descadastrados = repo.emails_descadastrados(sb)
            ids = [d["id"] for d in lote_atual]
            fila.marcar(sb, ids, "enviando")
            df = pd.DataFrame([{c: d["dados"].get(c, "") for c in COLUNAS} for d in lote_atual], columns=COLUNAS)
            anterior = {"s": 0, "e": 0, "i": 0}

            def progresso(feitos, resumo, lote_atual=lote_atual, anterior=anterior):
                pos = feitos - 1
                texto, _ = resumo.resultado.get(pos, ("Erro: sem resultado", ""))
                status = _status_do_texto(texto)
                fila.concluir_destino(sb, lote_atual[pos]["id"], status, texto)
                if status == "enviado":
                    ja_enviados.add(f"{lote_atual[pos]['protocolo']}|{lote_atual[pos]['email']}")
                contadores["enviados"] += resumo.sucessos - anterior["s"]
                contadores["erros"] += resumo.erros - anterior["e"]
                contadores["ignorados"] += resumo.ignorados - anterior["i"]
                anterior.update(s=resumo.sucessos, e=resumo.erros, i=resumo.ignorados)
                fila.renovar(sb, camp["id"], contadores)

            def parar():
                if relogio() >= prazo:
                    return True
                atual = fila.obter(sb, camp["id"])
                return not atual or atual["status"] != "rodando"

            resumo = campanha.executar_campanha(
                df, mapa, contas, enviados_hoje, descadastrados, ja_enviados, gerente, params,
                registrar=lambda *a: repo.registrar_envio(sb, *a), progresso=progresso, parar=parar,
                dormir=dormir, sortear=sortear,
                atribuicao=[d["dados"].get("_variante") for d in lote_atual])
            contadores["falhas_log"] += resumo.falhas_log
            # o que não foi processado volta para a fila
            nao_feitos = [lote_atual[i]["id"] for i in range(len(lote_atual)) if i not in resumo.resultado]
            fila.marcar(sb, nao_feitos, "pendente")
            if resumo.avisos:
                sb.table("campanhas").update({"aviso": " | ".join(resumo.avisos)[:500]}).eq("id", camp["id"]).execute()
            parada = resumo.motivo_parada
            if parada.startswith("Limite diário"):
                fila.liberar(sb, camp["id"], "pendente", "Limite diário das contas atingido: continua automaticamente "
                                                         "quando o limite renovar.", contadores)
                return "limite"
            if "erros seguidos" in parada:
                fila.liberar(sb, camp["id"], "pausada", parada + " Confira as contas e use Retomar.", contadores)
                return "pausada"
            if parada:  # interrompido por tempo ou por pausa/cancelamento feito na tela
                atual = fila.obter(sb, camp["id"])
                if atual and atual["status"] in ("pausada", "cancelada"):
                    fila.liberar(sb, camp["id"], atual["status"], atual.get("motivo"), contadores)
                    return atual["status"]
                fila.liberar(sb, camp["id"], "pendente", "Continua no próximo ciclo.", contadores)
                return "tempo"
    except Exception as erro:  # noqa: BLE001 — qualquer falha inesperada pausa a campanha em vez de repetir em loop
        fila.marcar(sb, [d["id"] for d in fila.em_andamento(sb, camp["id"])], "pendente")
        fila.liberar(sb, camp["id"], "pausada", f"Erro inesperado do trabalhador: {str(erro)[:200]}", contadores)
        raise


def rodar(sb, cofre, minutos=14, fabrica_smtp=None, relogio=time.monotonic, dormir=time.sleep, sortear=None, log=print):
    """Processa as campanhas em fila até acabar o tempo. Devolve (houve_trabalho, ainda_ha_o_que_fazer)."""
    prazo = relogio() + minutos * 60
    gerente = GerenteSMTP(fabrica_smtp) if fabrica_smtp else GerenteSMTP()
    houve, restante = False, False
    try:
        for camp in fila.candidatas(sb):
            motivo = processar_campanha(sb, camp, cofre, gerente, prazo, relogio, dormir, sortear)
            log(f"campanha {camp['id']} ({camp['nome']}): {motivo}")
            if motivo in ("concluida", "tempo", "pausada", "cancelada"):
                houve = True
            if motivo == "tempo":
                restante = True
                break
            if motivo in ("limite", "sem_conta"):  # as contas são compartilhadas: nada mais a fazer agora
                break
    finally:
        gerente.fechar()
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
        try:  # ainda tem e-mail na fila e o tempo acabou: chama o próximo ciclo na hora
            gatilho.disparar_workflow(env["GITHUB_REPOSITORY"], env["GITHUB_TOKEN"], gatilho.WORKFLOW_PADRAO,
                                      env.get("GITHUB_REF_NAME", "main"))
            print("Próximo ciclo acionado.")
        except gatilho.ErroGatilho as erro:
            print(f"Não consegui acionar o próximo ciclo ({erro}); o agendamento cuida disso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
