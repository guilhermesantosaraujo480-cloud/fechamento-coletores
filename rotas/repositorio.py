"""Banco de dados das rotas: coletores de rota, grupos, perfis de empresas e histórico de envios."""
import json

from core.consulta import buscar_todos
from core.utils import agora_br

from .perfis import PERFIS_PADRAO, Perfil


# ------------------------------------------------------------------ coletores de rota
def listar_coletores(sb, somente_ativos=False):
    q = sb.table("rota_coletores").select("*")
    if somente_ativos:
        q = q.eq("ativo", True)
    return q.order("nome_rota").execute().data or []


def criar_coletor(sb, nome_rota, telefone="", usuario_id=None):
    nome = nome_rota.strip().upper()
    if sb.table("rota_coletores").select("id").eq("nome_rota", nome).limit(1).execute().data:
        raise ValueError("Já existe um coletor de rota com esse nome.")
    sb.table("rota_coletores").insert({"nome_rota": nome, "telefone": telefone.strip(),
                                       "usuario_id": usuario_id, "ativo": True}).execute()


def atualizar_coletor(sb, coletor_id, **campos):
    sb.table("rota_coletores").update(campos).eq("id", coletor_id).execute()


# ---------------------------------------------------------------------------- grupos
def listar_grupos(sb, empresa=None):
    q = sb.table("rota_grupos").select("*").eq("ativo", True)
    if empresa:
        q = q.eq("empresa", empresa)
    return q.order("id").execute().data or []


def criar_grupo(sb, empresa, nome, destino):
    sb.table("rota_grupos").insert({"empresa": empresa, "nome": nome.strip(), "destino": destino.strip(),
                                    "ativo": True}).execute()


def remover_grupo(sb, grupo_id):
    sb.table("rota_grupos").update({"ativo": False}).eq("id", grupo_id).execute()


# --------------------------------------------------------------------------- perfis
def listar_perfis(sb):
    """Perfis padrão (Reintegra, TIM) + os criados na tela. Falha na tabela não impede de usar os padrão."""
    perfis = list(PERFIS_PADRAO)
    try:
        for linha in sb.table("rota_perfis").select("*").order("id").execute().data or []:
            d = linha["definicao"]
            perfis.append(Perfil.de_dict(json.loads(d) if isinstance(d, str) else d))
    except Exception:
        pass
    return perfis


def salvar_perfil(sb, perfil):
    sb.table("rota_perfis").insert({"nome": perfil.nome, "definicao": perfil.para_dict()}).execute()


# ------------------------------------------------------------------------- histórico
def registrar_envio(sb, usuario, empresa, data_rota, resultado, qtd):
    try:
        sb.table("rota_envios").insert({
            "data_hora": agora_br().isoformat(), "data_rota": str(data_rota), "empresa": empresa,
            "coletor": resultado.coletor, "qtd": int(qtd), "destino": resultado.destino,
            "status": resultado.status, "detalhe": resultado.detalhe[:300], "usuario": usuario,
        }).execute()
        return True
    except Exception:
        return False


def enviados_na_data(sb, empresa, data_rota):
    """Coletores que já receberam rota dessa empresa nessa data (evita mandar em dobro)."""
    linhas = buscar_todos(sb, "rota_envios", "id,coletor", {"empresa": empresa, "data_rota": str(data_rota), "status": "enviado"})
    return {r["coletor"] for r in linhas}


def historico(sb, limite=300):
    return sb.table("rota_envios").select("*").order("id", desc=True).limit(limite).execute().data or []
