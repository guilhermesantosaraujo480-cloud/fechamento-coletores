"""Consultas ao Supabase: paginação (limite de 1000 linhas) e filtros no servidor."""
from .utils import como_iso, dia_seguinte_iso


def aplicar_filtros(q, filtros=None, faixa=None):
    """filtros: {coluna: valor} (igualdade) ou {coluna: [valores]} (IN).
    faixa: (coluna, inicio, fim) com fim INCLUSIVO — funciona para colunas date, text ou timestamp."""
    for coluna, valor in (filtros or {}).items():
        if isinstance(valor, (list, tuple, set)):
            q = q.in_(coluna, list(valor))
        else:
            q = q.eq(coluna, valor)
    if faixa:
        coluna, ini, fim = faixa
        if ini:
            q = q.gte(coluna, como_iso(ini))
        if fim:
            q = q.lt(coluna, dia_seguinte_iso(fim))
    return q


def buscar_todos(sb, tabela, colunas="*", filtros=None, faixa=None, ordem="id",
                 decrescente=False, tamanho=1000, maximo=200000):
    """Busca TODAS as linhas (paginando de 1000 em 1000). Use uma coluna única em `ordem`."""
    resultado, inicio = [], 0
    while inicio < maximo:
        q = aplicar_filtros(sb.table(tabela).select(colunas), filtros, faixa)
        dados = (q.order(ordem, desc=decrescente)
                  .range(inicio, inicio + tamanho - 1).execute().data) or []
        resultado.extend(dados)
        if len(dados) < tamanho:
            break
        inicio += tamanho
    return resultado


def contar(sb, tabela, filtros=None, faixa=None):
    """Conta linhas sem baixar os dados."""
    q = aplicar_filtros(sb.table(tabela).select("id", count="exact"), filtros, faixa)
    res = q.limit(1).execute()
    contagem = getattr(res, "count", None)
    return int(contagem) if contagem is not None else len(res.data or [])
