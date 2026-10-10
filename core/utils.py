"""Funções pequenas e puras usadas em todo o sistema (fácil de testar)."""
import html
import re
from datetime import date, datetime, timedelta, timezone

try:  # horário oficial de Brasília (sem horário de verão desde 2019)
    from zoneinfo import ZoneInfo

    FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")
except Exception:  # ambiente sem banco de fusos: UTC-3 fixo
    FUSO_BRASILIA = timezone(timedelta(hours=-3))

PERIODOS = ["Quinzena atual", "Quinzena anterior", "Hoje", "Últimos 7 dias", "Últimos 30 dias", "Este mês",
            "Mês passado", "Personalizado"]


def agora_br():
    return datetime.now(FUSO_BRASILIA)


def hoje_br():
    return agora_br().date()


def brl(valor):
    """Formata em reais no padrão brasileiro: R$ 1.234,50 (negativos: -R$ 10,00)."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        v = 0.0
    if v != v:  # NaN
        v = 0.0
    texto = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {texto}" if v < 0 and round(abs(v), 2) > 0 else f"R$ {texto}"


def data_br(valor):
    """'2026-10-09' / date / datetime -> '09/10/2026'. Entrada inválida volta como texto."""
    if valor is None or valor == "":
        return ""
    try:
        if hasattr(valor, "strftime"):
            return valor.strftime("%d/%m/%Y")
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(valor)


def para_centavos(valor):
    """Dinheiro como inteiro de centavos evita erros de arredondamento de float."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return 0
    return 0 if v != v else int(round(v * 100))


def limites_quinzena(dia):
    """Quinzena que contém o dia: 1–15 ou 16–último dia do mês."""
    if dia.day <= 15:
        return dia.replace(day=1), dia.replace(day=15)
    primeiro_do_proximo = (dia.replace(day=28) + timedelta(days=4)).replace(day=1)
    return dia.replace(day=16), primeiro_do_proximo - timedelta(days=1)


def periodo_por_nome(nome, hoje):
    """Devolve (inicio, fim) para os atalhos de período."""
    if nome == "Quinzena atual":
        return limites_quinzena(hoje)
    if nome == "Quinzena anterior":
        return limites_quinzena(limites_quinzena(hoje)[0] - timedelta(days=1))
    if nome == "Hoje":
        return hoje, hoje
    if nome == "Últimos 7 dias":
        return hoje - timedelta(days=6), hoje
    if nome == "Últimos 30 dias":
        return hoje - timedelta(days=29), hoje
    if nome == "Mês passado":
        ultimo = hoje.replace(day=1) - timedelta(days=1)
        return ultimo.replace(day=1), ultimo
    return hoje.replace(day=1), hoje  # "Este mês" (padrão)


def escapar(texto):
    return html.escape(str(texto), quote=True)


def em_lotes(itens, tamanho):
    itens = list(itens)
    for i in range(0, len(itens), tamanho):
        yield itens[i:i + tamanho]


def como_iso(valor):
    """date/datetime/str -> 'AAAA-MM-DD'."""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)[:10]


def dia_seguinte_iso(valor):
    d = datetime.strptime(como_iso(valor), "%Y-%m-%d").date()
    return (d + timedelta(days=1)).isoformat()


def limpar_termo_busca(termo):
    """Remove caracteres que alterariam o filtro .or_() do PostgREST."""
    return re.sub(r"[%*,()\\\"'_]", " ", str(termo)).strip()


def serie_utc_para_br(serie):
    """Série de timestamps UTC (texto ISO) -> texto 'dd/mm/aaaa HH:MM:SS' em Brasília."""
    import pandas as pd

    dt = pd.to_datetime(serie, utc=True, errors="coerce")
    return dt.dt.tz_convert("America/Sao_Paulo").dt.strftime("%d/%m/%Y %H:%M:%S").fillna("")
