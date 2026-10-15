"""Sugestão de coletor para OS que ainda estão sem dono. Regras (explicáveis, nada de caixa-preta):

1. 'Cliente mudou-se' -> coletor de DEPÓSITO (se houver um).
2. OS que já foi à rua (tentativas ou último motivo) -> coletor de RETENTATIVAS (se houver um).
3. OS nova -> o coletor que já trabalha naquele bairro (pelo que já está distribuído na própria planilha);
   se não houver, pelo prefixo do CEP; depois, quem já atende aquela cidade e tem menos OS; por último, o menos carregado.
4. Ninguém passa de ~1,5x a média de OS novas: o excedente vai para o menos carregado.
"""
import math
from collections import Counter, defaultdict

import pandas as pd

from .processamento import SEM_COLETOR, chave_texto


def _cep5(cep):
    d = "".join(ch for ch in str(cep or "") if ch.isdigit())
    return d[:5]


def _territorio(can, atrib, normais):
    """{(cidade, bairro): Counter(coletor)} e {(cidade, cep5): Counter} só com coletores normais já atribuídos."""
    por_bairro, por_cep = defaultdict(Counter), defaultdict(Counter)
    for idx, c in atrib.items():
        if c not in normais:
            continue
        cid = chave_texto(can.at[idx, "cidade"])
        por_bairro[(cid, can.at[idx, "bairro_ef"])][c] += 1
        por_cep[(cid, _cep5(can.at[idx, "cep"]))][c] += 1
    return por_bairro, por_cep


def sugerir(can, atrib, tipos, receberao=None):
    """can: OS (com bairro_ef, cidade, cep, motivo). atrib: Série coletor atual (SEM_COLETOR = sem dono).
    tipos: {nome_rota: 'normal'|'retentativa'|'deposito'}. receberao: coletores normais que podem receber OS novas
    (padrão: todos os normais já presentes na planilha).
    Devolve DataFrame indexado como `can` com colunas `sugestao` e `razao` (só para as OS sem dono)."""
    sem = atrib[atrib == SEM_COLETOR].index
    normais_planilha = sorted({c for c in atrib.unique() if c != SEM_COLETOR and tipos.get(c, "normal") == "normal"})
    normais = list(receberao) if receberao else normais_planilha
    retentativa = next((c for c, t in tipos.items() if t == "retentativa"), None)
    deposito = next((c for c, t in tipos.items() if t == "deposito"), None)
    saida = pd.DataFrame({"sugestao": SEM_COLETOR, "razao": ""}, index=sem)
    if len(sem) == 0:
        return saida

    novas = []
    for idx in sem:
        motivo = chave_texto(can.at[idx, "motivo"])
        ja_foi = bool(motivo)  # só o último motivo/ocorrência prova que um coletor já foi lá (Qtd Ag. é agendamento)
        if "MUDOU" in motivo and deposito:
            saida.loc[idx] = [deposito, "mudou-se → depósito"]
        elif ja_foi and retentativa:
            saida.loc[idx] = [retentativa, "já foi à rua → retentativas"]
        else:
            novas.append(idx)
    if not novas:
        return saida
    if not normais:
        saida.loc[novas, "razao"] = "nenhum coletor normal disponível"
        return saida

    por_bairro, por_cep = _territorio(can, atrib, set(normais))
    atuam_na_cidade = defaultdict(set)  # cidade -> coletores normais que já trabalham nela
    for (cid, _), cont in por_bairro.items():
        atuam_na_cidade[cid].update(cont)
    carga = Counter({c: 0 for c in normais})
    limite = max(10, math.ceil(len(novas) / len(normais) * 1.5))

    # bairros maiores primeiro: ficam com o dono do território antes de a cota encher
    ordem = sorted(novas, key=lambda i: (can.at[i, "bairro_ef"], can.at[i, "cep"]))
    for idx in ordem:
        cid = chave_texto(can.at[idx, "cidade"])
        dono, razao = None, ""
        for fonte, chave, rotulo in ((por_bairro, (cid, can.at[idx, "bairro_ef"]), "já atende o bairro"),
                                     (por_cep, (cid, _cep5(can.at[idx, "cep"])), "já atende a região do CEP")):
            for c, _ in fonte.get(chave, Counter()).most_common():
                if carga[c] < limite:
                    dono, razao = c, rotulo
                    break
            if dono:
                break
        if dono is None:
            da_cidade = [c for c in normais if c in atuam_na_cidade.get(cid, ()) and carga[c] < limite]
            if da_cidade:
                dono, razao = min(da_cidade, key=lambda c: (carga[c], c)), "equilibrar carga (mesma cidade)"
            else:
                dono, razao = min(normais, key=lambda c: (carga[c], c)), "equilibrar carga (fora da região habitual)"
        carga[dono] += 1
        saida.loc[idx] = [dono, razao]
    return saida


def arquivo_para_plataforma(can, atrib, perfil, ignorar=(SEM_COLETOR,)):
    """Tabela simples [ID da OS, Coletor] para conferir/importar na plataforma. O formato exato de importação em massa
    de cada plataforma pode exigir outras colunas: ajuste aqui quando tivermos o modelo."""
    cab_id = next((cab for cab, campo in perfil.saida if campo == "id"), "ID")
    mascara = ~atrib.isin(list(ignorar))
    return pd.DataFrame({cab_id: can.loc[mascara, "id"], "Coletor": atrib[mascara]}).reset_index(drop=True)
