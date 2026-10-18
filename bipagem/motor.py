"""Orquestração da bipagem: decide a ordem, o ponto no serial, as repetições e quando parar.

Não conhece o navegador: fala com uma `plataforma` (ver reintegra.py) e com uma `api` (progresso/parada).
Por isso dá para testar tudo sem abrir o Chrome."""
import time

from .regras import MAX_PONTOS, Pool, codigo_do_equipamento, mais_um_ponto, pontos

ETAPAS = ("inicio", "aberta", "retirada", "bipado1", "bipado2", "finalizando")
SEGURA_ATE = ETAPAS.index("retirada")  # até aqui nada foi gravado na OS: dá para tentar de novo sozinho


class ErroSerial(Exception):
    pass


def _hoje():
    return time.strftime("%d/%m/%Y")  # a data da coleta é o dia da bipagem (confirmado)


def colocar_serial(plataforma, pool):
    """Digita o serial da vez; se a plataforma recusar (duplicado), acrescenta um ponto e tenta de novo."""
    serial = pool.atual()
    tentativas = 1
    resultado = plataforma.tentar_serial(serial, forte=False)
    while resultado != "ok":
        if pontos(serial) >= MAX_PONTOS:
            raise ErroSerial(f"Plataforma recusou '{serial}' mesmo com {MAX_PONTOS} pontos "
                             f"({getattr(plataforma, 'ultimo_alerta', '') or 'sem texto'}).")
        serial = mais_um_ponto(serial)
        tentativas += 1
        resultado = plataforma.tentar_serial(serial, forte=True)
    return serial, tentativas


def processar_os(plataforma, numero, pool, codigos, estado, hoje):
    """Uma OS inteira. `estado["etapa"]` diz até onde chegou (usado para decidir se pode tentar de novo)."""
    estado["etapa"] = "inicio"
    plataforma.abrir_os(numero)
    estado["etapa"] = "aberta"
    plataforma.iniciar_retirada()
    estado["etapa"] = "retirada"
    usados, tentativas = [], 0
    for i, codigo in enumerate(codigos):
        plataforma.selecionar_equipamento(codigo)
        serial, tent = colocar_serial(plataforma, pool)
        pool.consumir()  # a plataforma aceitou: este serial está gasto
        usados.append(serial)
        tentativas += tent
        estado["etapa"] = "bipado1" if i == 0 else "bipado2"
        plataforma.salvar_perifericos()
    estado["etapa"] = "finalizando"
    plataforma.finalizar(hoje)
    return usados, tentativas


def executar(lote, plataforma, api, log=print, hoje=_hoje, max_erros_seguidos=3):
    """Roda o lote até acabar. Devolve (status_final, mensagem): concluido | parado | erro."""
    codigos = [codigo_do_equipamento(lote["equip1"])]
    if int(lote["qtd_aparelhos"]) == 2:
        codigos.append(codigo_do_equipamento(lote["equip2"]))
    limite = int(lote["limite_ordens"])
    ok, erros = int(lote.get("ordens_ok") or 0), int(lote.get("ordens_erro") or 0)
    pool = Pool(lote["seriais"], lote.get("indice_pool") or 0)
    ignoradas, repetidas, seguidos = set(), {}, 0

    def salvar(msg=""):
        api.progresso(ordens_ok=ok, ordens_erro=erros, indice_pool=pool.indice, **({"mensagem": msg} if msg else {}))

    plataforma.abrir_lista()
    while True:
        api.sinal(f"lote {lote['id']}: {ok}/{limite}")
        if api.deve_parar():
            salvar("Parado a pedido. Clique em Retomar para continuar.")
            return "parado", "Parado a pedido."
        if ok >= limite:
            return "concluido", f"{ok} ordens bipadas."
        plataforma.garantir_sessao()
        candidatas = [o for o in plataforma.listar_os() if o not in ignoradas]
        if not candidatas:
            return "concluido", f"Não há mais OS 'Coletado App' na lista ({ok} de {limite} bipadas)."
        numero = candidatas[0]
        log(f"[{ok + 1}/{limite}] OS {numero}")
        estado = {"etapa": "inicio"}
        try:
            usados, tent = processar_os(plataforma, numero, pool, codigos, estado, hoje())
            plataforma.aguardar_retorno_lista()
            ainda_na_lista = numero in plataforma.listar_os()
        except Exception as erro:  # noqa: BLE001 — qualquer falha precisa ser tratada, nunca ignorada em silêncio
            msg = f"{type(erro).__name__}: {erro}"[:300]
            etapa = estado["etapa"]
            log(f"   ✖ falhou na etapa '{etapa}': {msg}")
            plataforma.registrar_falha(numero, msg)
            if ETAPAS.index(etapa) <= SEGURA_ATE and repetidas.get(numero, 0) < 1:
                repetidas[numero] = repetidas.get(numero, 0) + 1
                log("   ↻ nada foi gravado nessa OS; vou tentar mais uma vez")
            else:
                ignoradas.add(numero)
                erros += 1
                seguidos += 1
                gravou = ETAPAS.index(etapa) > SEGURA_ATE
                api.item(os=numero, status="verificar" if gravou else "erro", obs=f"etapa {etapa}: {msg}"
                         + (" — CONFIRA ESTA OS NA PLATAFORMA (já tinha serial gravado)" if gravou else ""))
                salvar()
            try:
                plataforma.recuperar()
            except Exception as erro2:  # noqa: BLE001
                salvar()
                return "erro", f"Não consegui voltar para a lista da plataforma: {erro2}"[:300]
            if seguidos >= max_erros_seguidos:
                return "erro", f"{seguidos} OS seguidas com erro: parei para você conferir (veja a coluna Obs)."
            continue

        seguidos = 0
        serial1, serial2 = usados[0], (usados[1] if len(usados) > 1 else "")
        if ainda_na_lista:  # clicou em finalizar, mas a OS continua na lista: não conta como feita
            ignoradas.add(numero)
            erros += 1
            api.item(os=numero, status="verificar", serial1=serial1, serial2=serial2, tentativas=tent,
                     obs="Finalizou, mas a OS continuou na lista — CONFIRE NA PLATAFORMA")
            log("   ⚠ a OS continuou na lista; marcada para conferência")
        else:
            ok += 1
            alterados = [u for u in usados if pontos(u) > 0]
            api.item(os=numero, status="ok", serial1=serial1, serial2=serial2, tentativas=tent,
                     obs=("serial com ponto (repetido)" if alterados else ""))
            log(f"   ✔ {' + '.join(usados)}")
        salvar()
