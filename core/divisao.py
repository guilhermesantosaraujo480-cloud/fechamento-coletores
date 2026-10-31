"""Divisão de uma coleta entre dois coletores que trabalham juntos com um só login (sem Streamlit; testável).

A coleta original continua existindo com a PARTE DO DONO (valor_total reduzido) e nasce uma segunda linha para o parceiro com a outra
parte. As duas mostram a quantidade total de aparelhos; os totais gerais contam esses aparelhos uma vez só (`fin.sem_duplicadas`).
Divisão meio a meio, em centavos: sobra de centavo fica com o dono. Só se divide coleta aprovada e ainda NÃO paga.
Colunas: coletas.divisao_de (só na linha do parceiro = id da original) e coletas.dividida_com (nas duas = nome do outro). migracao_v9.sql.
"""
COLUNAS = "id,data,coletor,quantidade,foto_url,status,valor_total,pago,qtd_acrescimo,divisao_de,dividida_com"


class ErroDivisao(ValueError):
    """Mensagem pronta para mostrar ao administrador."""


def partes(valor_total):
    """(parte do dono, parte do parceiro) em reais. Em centavos; o centavo que sobra fica com o dono."""
    centavos = int(round(float(valor_total) * 100))
    parceiro = centavos // 2
    return (centavos - parceiro) / 100, parceiro / 100


def motivo_de_nao_dividir(linha):
    """'' se a coleta pode ser dividida; senão o motivo (texto para a tela)."""
    if str(linha.get("status")) != "Aprovado":
        return "só coleta aprovada pode ser dividida"
    if linha.get("pago") in (True, "true", "True", "t"):
        return "já está marcada como paga"
    if linha.get("divisao_de") or str(linha.get("dividida_com") or "").strip():
        return "já foi dividida"
    if float(linha.get("valor_total") or 0) <= 0:
        return "sem valor para dividir"
    return ""


def _ler(sb, coleta_id):
    try:
        linhas = sb.table("coletas").select(COLUNAS).eq("id", int(coleta_id)).execute().data
    except Exception as erro:  # noqa: BLE001 — colunas novas ausentes
        raise ErroDivisao(f"Não consegui ler a coleta. Rode o `migracao_v9.sql` no Supabase. Detalhe: {erro}") from erro
    if not linhas:
        raise ErroDivisao(f"Coleta #{coleta_id} não encontrada.")
    return linhas[0]


def dividir(sb, coleta_id, parceiro):
    """Divide a coleta meio a meio com `parceiro`. Devolve (id da nova linha, parte do dono, parte do parceiro)."""
    parceiro = str(parceiro or "").strip()
    original = _ler(sb, coleta_id)
    if not parceiro:
        raise ErroDivisao("Escolha o coletor parceiro.")
    if parceiro == str(original["coletor"]):
        raise ErroDivisao("O parceiro precisa ser outro coletor.")
    motivo = motivo_de_nao_dividir(original)
    if motivo:
        raise ErroDivisao(f"Coleta #{coleta_id}: {motivo}.")
    dono_valor, parceiro_valor = partes(original["valor_total"])
    novo = {"data": original["data"], "coletor": parceiro, "quantidade": int(original["quantidade"] or 0), "foto_url": original["foto_url"],
            "status": "Aprovado", "valor_total": parceiro_valor, "pago": False, "qtd_acrescimo": 0,
            "divisao_de": int(original["id"]), "dividida_com": original["coletor"]}
    criada = sb.table("coletas").insert(novo).execute().data
    if not criada:
        raise ErroDivisao("Não consegui criar a parte do parceiro. Nada foi alterado.")
    novo_id = int(criada[0]["id"])
    try:  # a parte do dono só diminui DEPOIS de a do parceiro existir; se falhar, desfaz a nova linha
        mudou = sb.table("coletas").update({"valor_total": dono_valor, "dividida_com": parceiro}).eq("id", int(original["id"])).eq(
            "pago", False).execute().data
    except Exception as erro:  # noqa: BLE001
        sb.table("coletas").delete().eq("id", novo_id).execute()
        raise ErroDivisao(f"Não consegui atualizar a coleta original; a divisão foi cancelada. Detalhe: {erro}") from erro
    if not mudou:
        sb.table("coletas").delete().eq("id", novo_id).execute()
        raise ErroDivisao("A coleta mudou enquanto você dividia (talvez tenha sido marcada como paga). Nada foi alterado.")
    return novo_id, dono_valor, parceiro_valor


def desfazer(sb, filho_id):
    """Desfaz a divisão: devolve a parte do parceiro ao dono e apaga a linha do parceiro. Só se nenhuma das duas está paga."""
    filho = _ler(sb, filho_id)
    if not filho.get("divisao_de"):
        raise ErroDivisao("Esta linha não é a parte de um parceiro.")
    if filho.get("pago") in (True, "true", "True", "t"):
        raise ErroDivisao("A parte do parceiro já está marcada como paga. Desmarque o pagamento antes de desfazer.")
    pai = _ler(sb, filho["divisao_de"])
    if pai.get("pago") in (True, "true", "True", "t"):
        raise ErroDivisao("A coleta original já está marcada como paga. Desmarque o pagamento antes de desfazer.")
    if str(pai.get("dividida_com") or "").strip():  # (se já foi devolvida e só faltou apagar a linha do parceiro, não soma de novo)
        sb.table("coletas").update({"valor_total": round(float(pai["valor_total"]) + float(filho["valor_total"]), 2),
                                    "dividida_com": None}).eq("id", int(pai["id"])).execute()
    sb.table("coletas").delete().eq("id", int(filho["id"])).execute()
    return int(pai["id"])
