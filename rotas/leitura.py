"""Leitura da planilha da operadora. Tudo entra como TEXTO (telefone, CEP e número perdem zeros se virarem número)."""
import pandas as pd


def carregar_planilha(arquivo):
    """Aceita .xlsx/.xls de verdade e os '.xls' que na verdade são texto separado por TAB (Reintegra)."""
    nome = arquivo.name.lower()
    if nome.endswith((".xlsx", ".xlsm", ".xls")):
        try:
            arquivo.seek(0)
            return pd.read_excel(arquivo, dtype=str)
        except Exception:
            pass  # '.xls' que é texto
    for codificacao in ("latin1", "utf-8", "utf-8-sig", "cp1252"):
        for sep in ("\t", ";", ","):
            try:
                arquivo.seek(0)
                df = pd.read_csv(arquivo, sep=sep, encoding=codificacao, dtype=str)
                if len(df.columns) > 2:
                    return df
            except Exception:
                continue
    raise ValueError("Não consegui ler a planilha. Confira se é .xls, .xlsx ou .csv exportado do sistema.")
