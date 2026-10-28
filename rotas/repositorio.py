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


def tipos_dos_coletores(lista):
    """{nome_rota: 'normal'|'retentativa'|'deposito'} (coluna `tipo` pode não existir antes da migracao_v4)."""
    return {c["nome_rota"]: (c.get("tipo") or "normal") for c in lista}


def criar_coletor(sb, nome_rota, telefone="", usuario_id=None, tipo="normal"):
    nome = nome_rota.strip().upper()
    if sb.table("rota_coletores").select("id").eq("nome_rota", nome).limit(1).execute().data:
        raise ValueError("Já existe um coletor de rota com esse nome.")
    linha = {"nome_rota": nome, "telefone": telefone.strip(), "usuario_id": usuario_id, "ativo": True}
    if tipo != "normal":  # só manda a coluna nova quando é preciso (assim funciona mesmo sem a migracao_v4)
        linha["tipo"] = tipo
    sb.table("rota_coletores").insert(linha).execute()


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


# ------------------------------------------------------------------------ apelidos
def listar_apelidos(sb):
    """{nome normalizado como aparece no relatório: nome_rota}. Sem a tabela (migracao_v4) devolve vazio."""
    try:
        return {r["apelido"]: r["nome_rota"] for r in sb.table("rota_apelidos").select("*").execute().data or []}
    except Exception:
        return {}


def salvar_apelido(sb, apelido_normalizado, nome_rota):
    sb.table("rota_apelidos").upsert({"apelido": apelido_normalizado, "nome_rota": nome_rota}, on_conflict="apelido").execute()


def remover_apelido(sb, apelido_normalizado):
    sb.table("rota_apelidos").delete().eq("apelido", apelido_normalizado).execute()


# ------------------------------------------------------------------ fotografias diárias
def salvar_snapshot(sb, linhas, tamanho=500):
    """Grava (ou atualiza, se for o mesmo dia) as linhas. Devolve quantas foram gravadas."""
    for i in range(0, len(linhas), tamanho):
        sb.table("rota_snapshots").upsert(linhas[i:i + tamanho], on_conflict="chave").execute()
    return len(linhas)


def datas_de_snapshot(sb, empresa, quantas=7):
    """As datas mais recentes que têm fotografia (mais nova primeiro)."""
    datas, limite = [], None
    for _ in range(quantas):
        q = sb.table("rota_snapshots").select("data").eq("empresa", empresa)
        if limite:
            q = q.lt("data", limite)
        linhas = q.order("data", desc=True).limit(1).execute().data or []
        if not linhas:
            break
        datas.append(str(linhas[0]["data"])[:10])
        limite = datas[-1]
    return datas


def ler_snapshot(sb, empresa, data):
    return buscar_todos(sb, "rota_snapshots", "os_id,coletor,bairro,cidade,motivo,urgente",
                        {"empresa": empresa, "data": str(data)}, ordem="os_id")


def limpar_snapshots_antigos(sb, dias=60):
    """Mantém só os últimos `dias` (o banco gratuito é pequeno). Não levanta erro."""
    try:
        from datetime import timedelta
        from core.utils import hoje_br
        corte = str(hoje_br() - timedelta(days=dias))
        sb.table("rota_snapshots").delete().lt("data", corte).execute()
    except Exception:
        pass


# ----------------------------------------------------------- mensagens prontas do WhatsApp (migracao_v7.sql)
def listar_mensagens(sb):
    """Mensagens salvas pelo administrador [{id, nome, texto}]. Sem a tabela, devolve vazio (as prontas do sistema continuam)."""
    try:
        return sb.table("mensagens_rota").select("id,nome,texto").order("id").execute().data or []
    except Exception:
        return []


def salvar_mensagem(sb, nome, texto):
    sb.table("mensagens_rota").insert({"nome": nome.strip(), "texto": texto.strip()}).execute()


def remover_mensagem(sb, mensagem_id):
    sb.table("mensagens_rota").delete().eq("id", mensagem_id).execute()
