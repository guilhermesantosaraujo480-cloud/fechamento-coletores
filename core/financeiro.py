"""Regras financeiras. Tudo aqui é puro (pandas), sem Streamlit nem banco, e é testado.

Dinheiro é calculado em CENTAVOS inteiros: somar floats gera erros como 0,1 + 0,2 = 0,30000000000000004.
"""
from dataclasses import dataclass

import pandas as pd

from datetime import timedelta

from .utils import brl, data_br, limites_quinzena

STATUS = ("Pendente", "Aprovado", "Recusado")
COLS_COLETAS = ["id", "data", "coletor", "quantidade", "foto_url", "status", "valor_total", "pago"]
COLS_VALES = ["id", "data", "coletor", "valor_vale", "descricao", "foto_url"]
COLS_PREMIOS = ["id", "data", "coletor", "valor_premiacao", "descricao"]


# ----------------------------------------------------------------- normalização
def _preparar(linhas, colunas, numericas=(), inteiras=(), booleanas=(), textos=()):
    df = pd.DataFrame(linhas or [])
    for c in colunas:
        if c not in df.columns:
            df[c] = None
    for c in numericas:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)
    for c in inteiras:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")
    for c in booleanas:
        df[c] = df[c].map(lambda x: x is True or str(x).lower() in ("true", "t", "1")).astype(bool)
    for c in textos:
        df[c] = df[c].map(lambda x: "" if x is None or x != x else str(x))
    df["data"] = df["data"].map(lambda x: "" if x is None or x != x else str(x)[:10])
    return df.reset_index(drop=True)


def df_coletas(linhas):
    return _preparar(linhas, COLS_COLETAS, numericas=["valor_total"], inteiras=["quantidade"],
                     booleanas=["pago"], textos=["coletor", "status"])


def df_vales(linhas):
    return _preparar(linhas, COLS_VALES, numericas=["valor_vale"], textos=["coletor", "descricao"])


def df_premios(linhas):
    return _preparar(linhas, COLS_PREMIOS, numericas=["valor_premiacao"], textos=["coletor", "descricao"])


def _centavos(serie):
    return (pd.to_numeric(serie, errors="coerce").fillna(0.0) * 100).round().astype("int64")


def filtrar_coletor(df, coletor):
    if not coletor or coletor == "Todos" or df.empty:
        return df
    return df[df["coletor"] == coletor]


def filtrar_periodo(df, ini, fim):
    """Filtro por data (texto AAAA-MM-DD) — usado quando os dados já estão em memória."""
    if df.empty:
        return df
    return df[(df["data"] >= str(ini)[:10]) & (df["data"] <= str(fim)[:10])]


# ---------------------------------------------------------------------- cálculo
@dataclass(frozen=True)
class Fechamento:
    aparelhos: int = 0
    bruto: int = 0          # centavos — só coletas Aprovadas
    premios: int = 0
    vales: int = 0
    nao_pago: int = 0       # bruto aprovado ainda não marcado como pago
    pendentes: int = 0      # coletas aguardando aprovação (qtd de envios)

    @property
    def liquido(self):
        return self.bruto + self.premios - self.vales

    def reais(self, campo):
        return getattr(self, campo) / 100


def calcular_fechamento(coletas, vales, premios):
    aprovadas = coletas[coletas["status"] == "Aprovado"] if not coletas.empty else coletas
    bruto = int(_centavos(aprovadas["valor_total"]).sum()) if not aprovadas.empty else 0
    nao_pagas = aprovadas[~aprovadas["pago"]] if not aprovadas.empty else aprovadas
    return Fechamento(
        aparelhos=int(aprovadas["quantidade"].sum()) if not aprovadas.empty else 0,
        bruto=bruto,
        premios=int(_centavos(premios["valor_premiacao"]).sum()) if not premios.empty else 0,
        vales=int(_centavos(vales["valor_vale"]).sum()) if not vales.empty else 0,
        nao_pago=int(_centavos(nao_pagas["valor_total"]).sum()) if not nao_pagas.empty else 0,
        pendentes=int((coletas["status"] == "Pendente").sum()) if not coletas.empty else 0,
    )


def quinzenas_antes(ini, quantas=12):
    """As `quantas` quinzenas anteriores à data `ini` (da mais antiga para a mais recente)."""
    lista, ref = [], ini - timedelta(days=1)
    for _ in range(quantas):
        qi, qf = limites_quinzena(ref)
        lista.append((qi, min(qf, ini - timedelta(days=1))))
        ref = qi - timedelta(days=1)
    return lista[::-1]


def saldo_anterior(coletas, vales, premios, ini, quantas=12):
    """Saldo devedor que vem das quinzenas anteriores, por coletor, em centavos (0 ou negativo).

    Quinzena com líquido positivo é paga e zera o saldo; com líquido negativo (vales maiores que a produção)
    a dívida passa para a seguinte e é abatida automaticamente. Os dados devem cobrir as quinzenas anteriores.
    """
    saldo = {}
    nomes = set(coletas["coletor"]) | set(vales["coletor"]) | set(premios["coletor"])
    for qi, qf in quinzenas_antes(ini, quantas):
        c, v, p = (filtrar_periodo(d, qi, qf) for d in (coletas, vales, premios))
        for nome in nomes:
            f = calcular_fechamento(filtrar_coletor(c, nome), filtrar_coletor(v, nome), filtrar_coletor(p, nome))
            saldo[nome] = min(0, saldo.get(nome, 0) + f.liquido)
    return {n: v for n, v in saldo.items() if v < 0}


def resumo_por_coletor(coletas, vales, premios, coletores=(), saldos=None):
    """Uma linha por coletor (valores em reais). Inclui coletores sem movimento se informados.
    `saldos`: saída de saldo_anterior(); entra como 'Saldo anterior' e é abatido em 'A pagar'."""
    saldos = saldos or {}
    nomes = set(coletores) | set(coletas["coletor"]) | set(vales["coletor"]) | set(premios["coletor"]) | set(saldos)
    nomes = sorted(n for n in nomes if n)
    linhas = []
    for nome in nomes:
        f = calcular_fechamento(filtrar_coletor(coletas, nome), filtrar_coletor(vales, nome),
                                filtrar_coletor(premios, nome))
        linhas.append({
            "Coletor": nome, "Aparelhos": f.aparelhos, "Bruto": f.bruto / 100,
            "Premiações": f.premios / 100, "Vales": f.vales / 100,
            "Líquido": f.liquido / 100, "Saldo anterior": saldos.get(nome, 0) / 100,
            "A pagar": (f.liquido + saldos.get(nome, 0)) / 100, "Não pago": f.nao_pago / 100,
        })
    colunas = ["Coletor", "Aparelhos", "Bruto", "Premiações", "Vales", "Líquido", "Saldo anterior", "A pagar", "Não pago"]
    return pd.DataFrame(linhas, columns=colunas)


def adicionar_total(resumo):
    if resumo.empty:
        return resumo
    total = {"Coletor": "TOTAL GERAL"}
    for c in resumo.columns[1:]:
        total[c] = round(float(resumo[c].sum()), 2) if c != "Aparelhos" else int(resumo[c].sum())
    return pd.concat([resumo, pd.DataFrame([total])], ignore_index=True)


def serie_diaria(coletas, ini, fim):
    """Aparelhos aprovados por dia (ou por mês se o período passar de ~3 meses). Índice = datas."""
    ini_d, fim_d = pd.Timestamp(str(ini)[:10]), pd.Timestamp(str(fim)[:10])
    dias = pd.date_range(ini_d, fim_d, freq="D")
    base = pd.Series(0, index=dias, dtype="int64")
    aprov = coletas[coletas["status"] == "Aprovado"] if not coletas.empty else coletas
    if not aprov.empty:
        por_dia = aprov.groupby(pd.to_datetime(aprov["data"], errors="coerce"))["quantidade"].sum()
        por_dia = por_dia[por_dia.index.notna()]
        base = base.add(por_dia, fill_value=0).astype("int64")
        base = base.reindex(dias, fill_value=0)
    if len(dias) > 92:
        base = base.resample("MS").sum()
    return base.to_frame("Aparelhos")


def texto_recibo(coletor, ini, fim, f, gerado_em, saldo_ant=0):
    saldo_txt = (f"↩️ *Saldo anterior (vales a descontar):* {brl(saldo_ant / 100)}\n"
                 f"💵 *A pagar:* {brl((f.liquido + saldo_ant) / 100)}\n-----------------------------\n") if saldo_ant else ""
    return (
        f"*FECHAMENTO DE COLETAS*\n"
        f"*Coletor:* {coletor}\n"
        f"*Período:* {data_br(ini)} até {data_br(fim)}\n"
        f"-----------------------------\n"
        f"📱 *Total de Aparelhos:* {f.aparelhos} un\n"
        f"💰 *Total Bruto:* {brl(f.bruto / 100)}\n"
        f"🎁 *Premiações/Extras:* {brl(f.premios / 100)}\n"
        f"📉 *Desconto em Vales:* {brl(f.vales / 100)}\n"
        f"-----------------------------\n"
        f"🧮 *Valor Líquido:* {brl(f.liquido / 100)}\n"
        f"-----------------------------\n"
        f"{saldo_txt}"
        f"Gerado em: {gerado_em.strftime('%d/%m/%Y às %H:%M')}"
    )


def formatar_moeda(df, colunas):
    """Cópia do DataFrame com as colunas em R$ (para exibição; não use para cálculo)."""
    out = df.copy()
    for c in colunas:
        if c in out.columns:
            out[c] = out[c].map(brl)
    return out
