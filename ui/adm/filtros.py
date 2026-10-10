"""Filtros globais (período e coletor) na barra lateral — valem para todas as páginas financeiras."""
from dataclasses import dataclass
from datetime import date

import streamlit as st

from core.utils import PERIODOS, data_br, hoje_br, periodo_por_nome


@dataclass(frozen=True)
class Filtro:
    ini: date
    fim: date
    coletor: str = "Todos"

    @property
    def descricao(self):
        quem = "todos os coletores" if self.coletor == "Todos" else self.coletor
        return f"{data_br(self.ini)} a {data_br(self.fim)} · {quem}"


def filtros_sidebar(coletores):
    hoje = hoje_br()
    with st.sidebar:
        st.markdown("##### 🔍 Filtros")
        nome = st.selectbox("Período", PERIODOS, index=PERIODOS.index("Este mês"), key="f_periodo")
        if nome == "Personalizado":
            ini = st.date_input("De", value=hoje.replace(day=1), key="f_ini", format="DD/MM/YYYY")
            fim = st.date_input("Até", value=hoje, key="f_fim", format="DD/MM/YYYY")
            if ini > fim:
                st.warning("A data inicial era maior que a final — troquei as duas.")
                ini, fim = fim, ini
        else:
            ini, fim = periodo_por_nome(nome, hoje)
            st.caption(f"{data_br(ini)} → {data_br(fim)}")
        opcoes = ["Todos"] + list(coletores)
        coletor = st.selectbox("Coletor", opcoes, key="f_coletor")
        if coletor not in opcoes:
            coletor = "Todos"
    return Filtro(ini, fim, coletor)
