"""Leitura das configurações (st.secrets) sem quebrar quando a chave não existe."""


def cfg(chave, padrao=""):
    try:
        import streamlit as st

        valor = st.secrets.get(chave, padrao)
        return padrao if valor is None else valor
    except Exception:
        return padrao


def cfg_float(chave, padrao):
    texto = str(cfg(chave, padrao)).replace("R$", "").replace(",", ".").strip()
    try:
        return float(texto)
    except ValueError:
        return float(padrao)


def valor_por_coleta():
    """Valor pago por aparelho. Pode ser mudado nos secrets (VALOR_POR_COLETA)."""
    return cfg_float("VALOR_POR_COLETA", 10.0)
