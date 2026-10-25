"""Carregamento de dados com cache curto. Toda gravação deve chamar `invalidar()`."""
from datetime import timedelta

import streamlit as st

from . import armazenamento as arm
from . import financeiro as fin
from .consulta import buscar_todos, contar


def _buscar(sb, tabela, colunas, **kw):
    """Traz só as colunas usadas (menos dados trafegados). Se alguma coluna nova ainda não existir no banco
    (SQL de migração não rodado), cai para `*` em vez de quebrar a tela."""
    try:
        return buscar_todos(sb, tabela, ",".join(colunas), **kw)
    except Exception:
        return buscar_todos(sb, tabela, "*", **kw)


@st.cache_data(ttl=30, show_spinner=False)
def carregar_financeiro(_sb, ini, fim, coletor="Todos"):
    """Coletas, vales e premiações do PERÍODO (filtrados no servidor) + todas as pendentes (qualquer data).
    Devolve (coletas, vales, premiacoes, pendentes) como DataFrames."""
    filtro = {} if coletor in (None, "", "Todos") else {"coletor": coletor}
    faixa = lambda: ("data", ini, fim)  # noqa: E731
    coletas = fin.df_coletas(_buscar(_sb, "coletas", fin.COLS_COLETAS, filtros=filtro, faixa=faixa()))
    vales = fin.df_vales(_buscar(_sb, "vales_coleta", fin.COLS_VALES, filtros=filtro, faixa=faixa()))
    premios = fin.df_premios(_buscar(_sb, "premiacoes", fin.COLS_PREMIOS, filtros=filtro, faixa=faixa()))
    pendentes = fin.df_coletas(_buscar(_sb, "coletas", fin.COLS_COLETAS, filtros={**filtro, "status": "Pendente"}))
    return coletas, vales, premios, pendentes


@st.cache_data(ttl=300, show_spinner=False)  # quinzenas passadas quase não mudam; toda gravação limpa este cache
def saldos_anteriores(_sb, ini, coletor="Todos"):
    """Saldo devedor (centavos, por coletor) que vem das quinzenas anteriores a `ini`."""
    inicio, fim = fin.quinzenas_antes(ini)[0][0], ini - timedelta(days=1)
    filtro = {} if coletor in (None, "", "Todos") else {"coletor": coletor}
    faixa = ("data", inicio, fim)
    # só o que o cálculo usa: sem fotos, sem descrições e sem a lista de pendentes
    coletas = fin.df_coletas(_buscar(_sb, "coletas", ["id", "data", "coletor", "quantidade", "status", "valor_total",
                                                      "pago", "qtd_acrescimo"], filtros=filtro, faixa=faixa))
    vales = fin.df_vales(_buscar(_sb, "vales_coleta", ["id", "data", "coletor", "valor_vale"], filtros=filtro, faixa=faixa))
    premios = fin.df_premios(_buscar(_sb, "premiacoes", ["id", "data", "coletor", "valor_premiacao"], filtros=filtro, faixa=faixa))
    return fin.saldo_anterior(coletas, vales, premios, ini)


@st.cache_data(ttl=30, show_spinner=False)
def carregar_extrato(_sb, nome, ini, fim):
    """Dados de UM coletor no período + quantas coletas dele aguardam aprovação (em qualquer data)."""
    filtro, faixa = {"coletor": nome}, ("data", ini, fim)
    coletas = fin.df_coletas(_buscar(_sb, "coletas", fin.COLS_COLETAS, filtros=filtro, faixa=faixa))
    vales = fin.df_vales(_buscar(_sb, "vales_coleta", fin.COLS_VALES, filtros=filtro, faixa=faixa))
    premios = fin.df_premios(_buscar(_sb, "premiacoes", fin.COLS_PREMIOS, filtros=filtro, faixa=faixa))
    pendentes = contar(_sb, "coletas", {"coletor": nome, "status": "Pendente"})
    return coletas, vales, premios, pendentes


@st.cache_data(ttl=30, show_spinner=False)
def ultimos_envios(_sb, nome, quantos=8):
    """Últimos envios de UM coletor (cache curto: mexer na quantidade/foto não consulta o banco de novo)."""
    return (_sb.table("coletas").select("id,data,quantidade,valor_total,status")
               .eq("coletor", nome).order("id", desc=True).limit(quantos).execute().data) or []


@st.cache_data(ttl=30, show_spinner=False)
def contar_pendentes(_sb):
    """Quantas coletas aguardam aprovação (qualquer data) — usado no selo da barra lateral."""
    return contar(_sb, "coletas", {"status": "Pendente"})


@st.cache_data(ttl=120, show_spinner=False)
def listar_usuarios(_sb):
    """Usuários SEM os hashes de senha/token. Funciona com ou sem a coluna `ativo`."""
    try:
        linhas = _sb.table("usuarios").select("id,usuario,nome_completo,cargo,ativo").order("nome_completo").execute().data
        return [{**u, "ativo": u.get("ativo") is not False} for u in (linhas or [])], True
    except Exception:
        linhas = _sb.table("usuarios").select("id,usuario,nome_completo,cargo").order("nome_completo").execute().data
        return [{**u, "ativo": True} for u in (linhas or [])], False


def nomes_coletores(_sb, somente_ativos=True):
    usuarios, _ = listar_usuarios(_sb)
    return [u["nome_completo"] for u in usuarios
            if u.get("cargo") == "COLETOR" and (u.get("ativo") is not False or not somente_ativos)]


@st.cache_data(ttl=3000, show_spinner=False)
def url_foto(_sb, valor, miniatura=False):
    """Link que o st.image consegue abrir (assina o link se a foto estiver no bucket privado).
    miniatura=True devolve a versão pequena quando a foto tem uma (fotos novas); senão, a foto inteira."""
    tipo, ref = arm.referencia_foto(valor)
    if tipo == "url":
        return ref
    if tipo == "caminho":
        return arm.link_assinado(_sb, (arm.caminho_miniatura(ref) if miniatura else None) or ref)
    return None


def tem_miniatura(valor):
    tipo, ref = arm.referencia_foto(valor)
    return tipo == "caminho" and arm.caminho_miniatura(ref) is not None


def invalidar():
    carregar_financeiro.clear()
    carregar_extrato.clear()
    ultimos_envios.clear()
    saldos_anteriores.clear()
    contar_pendentes.clear()
    listar_usuarios.clear()
