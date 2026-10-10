"""Geração de arquivos Excel."""
import re
from io import BytesIO

import pandas as pd

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_NUMERO_SIMPLES = re.compile(r"-[\d\sR$.,]+$")


def neutralizar_formulas(df):
    """Células que começam com = + @ viram texto: evita 'injeção de fórmula' vinda de planilhas de clientes."""
    out = df.copy()

    def seguro(v):
        if isinstance(v, str) and v:
            if v[0] in "=+@\t\r" or (v[0] == "-" and not _NUMERO_SIMPLES.match(v)):
                return "'" + v
        return v

    for c in out.columns:
        if out[c].dtype == object or str(out[c].dtype).startswith("str"):
            out[c] = out[c].map(seguro)
    return out


def gerar_excel(abas):
    """abas: {'Nome da aba': DataFrame}. Devolve os bytes do .xlsx."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
        for nome, df in abas.items():
            nome = re.sub(r"[\[\]:*?/\\]", "-", str(nome))[:31] or "Dados"
            neutralizar_formulas(df).to_excel(escritor, index=False, sheet_name=nome)
            ws = escritor.sheets[nome]
            ws.freeze_panes = "A2"
            for coluna in ws.columns:
                maior = max((len(str(c.value)) for c in coluna if c.value is not None), default=8)
                ws.column_dimensions[coluna[0].column_letter].width = min(max(10, maior + 2), 60)
    return buffer.getvalue()
