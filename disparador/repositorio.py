"""Acesso ao banco para o disparador (contas, envios, modelos, descadastros, cliques).
Erros de leitura SOBEM para quem chamou: esconder uma falha aqui faria o sistema ignorar limites e descadastros."""
import re
from datetime import timezone

from core.consulta import buscar_todos
from core.utils import agora_br, em_lotes

from .templates import WHATS_PADRAO


def agora_utc_iso():
    return agora_br().astimezone(timezone.utc).isoformat()


def inicio_do_dia_utc_iso():
    ini = agora_br().replace(hour=0, minute=0, second=0, microsecond=0)
    return ini.astimezone(timezone.utc).isoformat()


# ------------------------------------------------------------------ contas
def carregar_contas_ativas(sb, cofre):
    """(contas utilizáveis, contas ignoradas por senha ilegível)."""
    linhas = sb.table("contas_email").select("*").eq("ativa", True).order("id").execute().data or []
    contas, sem_senha = [], []
    for c in linhas:
        c["_senha"] = cofre.revelar(c.get("senha_app"))
        (contas if c["_senha"] else sem_senha).append(c)
    return contas, sem_senha


def listar_contas(sb):
    return sb.table("contas_email").select("id,email,nome_remetente,limite_diario,ativa,senha_app").order("id").execute().data or []


def criar_conta(sb, cofre, email, senha_app, nome_remetente, limite):
    sb.table("contas_email").insert({
        "email": email, "senha_app": cofre.proteger(senha_app), "nome_remetente": nome_remetente,
        "limite_diario": int(limite), "ativa": True,
    }).execute()


def alternar_conta(sb, conta_id, ativa):
    sb.table("contas_email").update({"ativa": bool(ativa)}).eq("id", conta_id).execute()


def proteger_senhas_existentes(sb, cofre, contas):
    n = 0
    for c in contas:
        if c.get("senha_app") and not cofre.esta_protegida(c["senha_app"]):
            sb.table("contas_email").update({"senha_app": cofre.proteger(c["senha_app"])}).eq("id", c["id"]).execute()
            n += 1
    return n


# ------------------------------------------------------------------ envios
def contar_enviados_hoje(sb):
    regs = _enviados_desde(sb, inicio_do_dia_utc_iso())
    cont = {}
    for r in regs:
        cont[r["conta"]] = cont.get(r["conta"], 0) + 1
    return cont


def _enviados_desde(sb, inicio_iso):
    resultado, inicio = [], 0
    while True:
        dados = (sb.table("envios_email").select("id,conta").eq("status", "enviado")
                   .gte("data_hora", inicio_iso).order("id").range(inicio, inicio + 999).execute().data) or []
        resultado.extend(dados)
        if len(dados) < 1000:
            return resultado
        inicio += 1000


_PROTOCOLO_SIMPLES = re.compile(r"^[\w.\-/]+$")
MAX_PROTOCOLOS_FILTRADOS = 20000


def ja_enviados(sb, protocolos=None):
    """Conjunto 'protocolo|e-mail' de quem já recebeu. Com `protocolos` (os da campanha em andamento) consulta só eles:
    o resultado vale o mesmo para a triagem, mas não cresce junto com o histórico inteiro (que pode ter 100 mil linhas).
    Se algum protocolo tiver caracteres estranhos, volta a ler o histórico todo (nunca arrisca reenviar)."""
    protocolos = None if protocolos is None else list(protocolos)
    if protocolos is not None and protocolos and all(str(p).strip() for p in protocolos):  # linha sem protocolo: lê tudo
        unicos = sorted({str(p).strip() for p in protocolos})
        if len(unicos) <= MAX_PROTOCOLOS_FILTRADOS and all(_PROTOCOLO_SIMPLES.match(p) for p in unicos):
            regs = []
            for lote in em_lotes(unicos, 150):
                regs.extend(buscar_todos(sb, "envios_email", "id,protocolo,email", {"status": "enviado", "protocolo": lote}))
            return {f"{r['protocolo']}|{r['email']}" for r in regs}
    regs = buscar_todos(sb, "envios_email", "id,protocolo,email", {"status": "enviado"})
    return {f"{r['protocolo']}|{r['email']}" for r in regs}


def registrar_envio(sb, envio_id, dados, conta_email, modelo_nome, status, erro=""):
    """True se gravou. Nunca levanta erro (um e-mail já saiu; o histórico não pode derrubar a campanha)."""
    try:
        sb.table("envios_email").insert({
            "envio_id": envio_id, "protocolo": dados["protocolo"], "email": dados["email"],
            "nome": dados["nome"], "conta": conta_email, "modelo": modelo_nome,
            "status": status, "erro": str(erro)[:300], "data_hora": agora_utc_iso(),
        }).execute()
        return True
    except Exception:
        return False


def historico(sb, limite=1000):
    return (sb.table("envios_email").select("id,envio_id,data_hora,nome,email,protocolo,conta,modelo,status,erro")
              .order("data_hora", desc=True).limit(limite).execute().data) or []


# ------------------------------------------------------------------ modelos
def listar_modelos(sb, somente_ativos=False):
    q = sb.table("modelos_email").select("*")
    if somente_ativos:
        q = q.eq("ativo", True)
    return q.order("id").execute().data or []


def salvar_modelo(sb, nome, assunto, texto, regras):
    sb.table("modelos_email").insert({
        "nome": nome.strip(), "assunto": assunto.strip(), "texto": texto.strip(),
        "regras": regras.strip(), "texto_whats": WHATS_PADRAO, "ativo": True,
    }).execute()


def alternar_modelo(sb, modelo_id, ativo):
    sb.table("modelos_email").update({"ativo": bool(ativo)}).eq("id", modelo_id).execute()


def excluir_modelo(sb, modelo_id):
    sb.table("modelos_email").delete().eq("id", modelo_id).execute()


# ------------------------------------------------------------- descadastros
def listar_descadastros(sb):
    return buscar_todos(sb, "descadastros", "*", ordem="email")


def emails_descadastrados(sb):
    return {r["email"].lower() for r in listar_descadastros(sb)}


def adicionar_descadastros(sb, emails, motivo="pediu para sair"):
    sb.table("descadastros").upsert(
        [{"email": e, "motivo": motivo, "data_hora": agora_utc_iso()} for e in sorted(emails)],
        on_conflict="email").execute()


def remover_descadastro(sb, email):
    sb.table("descadastros").delete().eq("email", email).execute()


# ------------------------------------------------------------------- já chamado (quem clicou)
def chamados(sb):
    """Conjunto 'protocolo|e-mail' de quem você já chamou (tabela cliques_chamados, migracao_v7.sql). Vazio se a tabela não existir."""
    try:
        return {f"{r['protocolo']}|{str(r['email']).lower()}" for r in buscar_todos(sb, "cliques_chamados", "protocolo,email", ordem="protocolo")}
    except Exception:  # noqa: BLE001 — sem a tabela, só não marca; a lista continua funcionando
        return set()


def marcar_chamados(sb, itens, por="", canal="whatsapp"):
    """itens: lista de (protocolo, email). Levanta erro se a tabela não existir (a tela avisa)."""
    linhas = [{"protocolo": str(p), "email": str(e).lower(), "canal": canal, "por": por, "data_hora": agora_utc_iso()} for p, e in itens]
    if linhas:
        sb.table("cliques_chamados").upsert(linhas, on_conflict="protocolo,email").execute()
    return len(linhas)


def desmarcar_chamado(sb, protocolo, email):
    sb.table("cliques_chamados").delete().eq("protocolo", str(protocolo)).eq("email", str(email).lower()).execute()


# ------------------------------------------------------------------- cliques
def listar_cliques(sb, desde=None):
    """Cliques registrados (desde = data inicial; a coluna de data é `data_clique` na tabela atual, `data_hora` em versões antigas;
    se nenhuma existir, lê tudo)."""
    if desde is not None:
        for coluna in ("data_clique", "data_hora"):
            try:
                return buscar_todos(sb, "cliques_email", "*", faixa=(coluna, desde, None), ordem="id")
            except Exception:  # noqa: BLE001 — tabela sem essa coluna: tenta a outra e, por fim, lê tudo
                continue
    try:
        return buscar_todos(sb, "cliques_email", "*", ordem="id")
    except Exception:  # tabela sem coluna `id`: leitura simples (limitada pelo Supabase a 1000 linhas)
        return sb.table("cliques_email").select("*").execute().data or []
