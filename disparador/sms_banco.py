"""Banco do SMS: celulares (gateways), fila de campanhas, histórico e lista de "SAIR". Sem Streamlit (testável).

Mesmo desenho da fila de e-mails (campanhas/campanha_destinos), mas em tabelas próprias (`sms_*`, ver migracao_v7.sql):
o e-mail que já funciona não é tocado. Erros de leitura SOBEM para quem chamou, porque esconder uma falha aqui faria o
sistema ignorar limites e a lista de "SAIR".
"""
from datetime import datetime, timedelta, timezone

from core.consulta import buscar_todos
from core.utils import em_lotes

from . import sms
from .repositorio import agora_utc_iso, inicio_do_dia_utc_iso

STATUS_ATIVOS = ("pendente", "rodando")
ROTULO = {"pendente": "⏳ Na fila", "rodando": "🟢 Enviando", "pausada": "⏸️ Pausada", "concluida": "✅ Concluída",
          "cancelada": "🛑 Cancelada", "agendada": "🕘 Agendada"}
LOTE_INSERCAO = 500


def _agora():
    return datetime.now(timezone.utc)


def agora_iso():
    return _agora().isoformat()


def _em(segundos):
    return (_agora() + timedelta(seconds=segundos)).isoformat()


def _completar(c):
    if c:
        for k in ("total", "enviados", "erros", "ignorados"):
            c[k] = int(c.get(k) or 0)
    return c


def esta_agendada(c, agora=None):
    """True se a campanha ainda espera a hora marcada para começar."""
    quando = c.get("agendada_para")
    return bool(quando) and str(quando) > (agora or _agora()).isoformat()


def rotulo(c):
    return ROTULO["agendada"] if c.get("status") == "pendente" and esta_agendada(c) else ROTULO.get(c.get("status"), c.get("status"))


# =========================================================================== celulares
def listar_gateways(sb):
    return sb.table("sms_gateways").select("id,nome,url_base,usuario,sim_numero,limite_diario,ativo,senha").order("id").execute().data or []


def criar_gateway(sb, cofre, nome, url_base, usuario, senha, sim_numero=None, limite_diario=100):
    sb.table("sms_gateways").insert({
        "nome": nome.strip(), "url_base": (url_base or "").strip() or "https://api.sms-gate.app", "usuario": usuario.strip(),
        "senha": cofre.proteger(senha.strip()), "sim_numero": int(sim_numero) if sim_numero else None,
        "limite_diario": int(limite_diario), "ativo": True,
    }).execute()


def alternar_gateway(sb, gateway_id, ativo):
    sb.table("sms_gateways").update({"ativo": bool(ativo)}).eq("id", gateway_id).execute()


def mudar_limite_gateway(sb, gateway_id, limite):
    sb.table("sms_gateways").update({"limite_diario": int(limite)}).eq("id", gateway_id).execute()


def remover_gateway(sb, gateway_id):
    sb.table("sms_gateways").delete().eq("id", gateway_id).execute()


def carregar_gateways_ativos(sb, cofre):
    """(celulares utilizáveis, celulares ignorados por senha ilegível). Cada um ganha `_senha`."""
    linhas = sb.table("sms_gateways").select("*").eq("ativo", True).order("id").execute().data or []
    uteis, sem_senha = [], []
    for g in linhas:
        g["_senha"] = cofre.revelar(g.get("senha"))
        (uteis if g["_senha"] else sem_senha).append(g)
    return uteis, sem_senha


# =========================================================================== histórico
def enviados_hoje(sb):
    """{gateway_id: quantos SMS saíram hoje} (limite diário de cada celular)."""
    cont, inicio = {}, 0
    ini = inicio_do_dia_utc_iso()
    while True:
        dados = (sb.table("sms_envios").select("id,gateway_id").eq("status", "enviado").gte("data_hora", ini)
                   .order("id").range(inicio, inicio + 999).execute().data) or []
        for r in dados:
            cont[r["gateway_id"]] = cont.get(r["gateway_id"], 0) + 1
        if len(dados) < 1000:
            return cont
        inicio += 1000


def ja_enviados(sb, protocolos):
    """Conjunto 'protocolo|telefone' de quem já recebeu SMS (só dos protocolos informados)."""
    unicos = sorted({str(p).strip() for p in protocolos if str(p).strip()})
    achados = set()
    for lote in em_lotes(unicos, 150):
        for r in buscar_todos(sb, "sms_envios", "id,protocolo,telefone", {"status": "enviado", "protocolo": lote}):
            achados.add(f"{r['protocolo']}|{sms.normalizar_bloqueio(r['telefone'])}")
    return achados


def registrar_envio(sb, camp_id, destino, texto, modelo, gateway, status, erro="", msg_id=""):
    """True se gravou. Nunca levanta erro (o SMS já saiu; o histórico não pode derrubar a campanha)."""
    try:
        sb.table("sms_envios").insert({
            "campanha_id": camp_id, "protocolo": destino.get("protocolo", ""), "telefone": destino.get("telefone", ""),
            "nome": destino.get("nome", ""), "texto": texto, "modelo": modelo, "gateway_id": gateway["id"] if gateway else None,
            "gateway_nome": gateway["nome"] if gateway else "", "status": status, "erro": str(erro)[:300],
            "msg_id": msg_id, "data_hora": agora_utc_iso()}).execute()
        return True
    except Exception:  # noqa: BLE001
        return False


COLUNAS_HISTORICO = "id,data_hora,nome,telefone,protocolo,gateway_nome,modelo,status,erro,texto"
ESTADOS_FINAIS = ("Delivered", "Failed")


def historico(sb, limite=500):
    """Últimos SMS (com a coluna `estado` quando a migracao_v7.sql já foi rodada)."""
    for colunas in (COLUNAS_HISTORICO + ",estado", COLUNAS_HISTORICO):
        try:
            return sb.table("sms_envios").select(colunas).order("data_hora", desc=True).limit(limite).execute().data or []
        except Exception:  # noqa: BLE001 — sem a coluna nova, cai para a lista antiga
            continue
    return []


def atualizar_estados(sb, cofre, limite=100, abrir=None):
    """Pergunta ao app do celular o que aconteceu com os últimos SMS (Delivered/Failed/Sent...) e guarda em `estado`.
    Devolve {estado: quantos}. Levanta ValueError se a coluna `estado` não existir (rodar a migracao_v7.sql)."""
    linhas = (sb.table("sms_envios").select("id,gateway_id,msg_id,estado").eq("status", "enviado")
                .order("id", desc=True).limit(int(limite)).execute().data) or []
    pendentes = [r for r in linhas if r.get("msg_id") and r.get("estado") not in ESTADOS_FINAIS]
    clientes, contagem = {}, {}
    por_id = {g["id"]: g for g in listar_gateways(sb)}
    from . import sms_gateway  # import tardio: o módulo do banco não precisa do cliente HTTP para o resto
    for r in pendentes:
        g = por_id.get(r["gateway_id"])
        if g is None:
            continue
        if g["id"] not in clientes:
            clientes[g["id"]] = sms_gateway.criar(g, cofre, abrir)
        cliente = clientes[g["id"]]
        if cliente is None:
            continue
        estado = cliente.consultar(r["msg_id"])
        if not estado:
            continue
        contagem[estado] = contagem.get(estado, 0) + 1
        if estado != r.get("estado"):
            try:
                sb.table("sms_envios").update({"estado": estado}).eq("id", r["id"]).execute()
            except Exception as erro:  # noqa: BLE001
                raise ValueError("Não consegui gravar o estado (rodou o `migracao_v7.sql` novo, com a coluna `estado`?)") from erro
    return contagem


# =========================================================================== lista de SAIR
def telefones_descadastrados(sb):
    return {sms.normalizar_bloqueio(r["telefone"]) for r in buscar_todos(sb, "sms_descadastros", "*", ordem="telefone")}


def listar_descadastros(sb):
    return buscar_todos(sb, "sms_descadastros", "*", ordem="telefone")


def adicionar_descadastros(sb, telefones, motivo="pediu para sair"):
    chaves = sorted({sms.normalizar_bloqueio(t) for t in telefones if sms.normalizar_bloqueio(t)})
    if chaves:
        sb.table("sms_descadastros").upsert([{"telefone": t, "motivo": motivo, "data_hora": agora_utc_iso()} for t in chaves],
                                            on_conflict="telefone").execute()
    return len(chaves)


def remover_descadastro(sb, telefone):
    sb.table("sms_descadastros").delete().eq("telefone", telefone).execute()


# =========================================================================== campanhas
def criar_campanha(sb, usuario, nome, textos, ctx, delay_min, delay_max, janela, domingo, sem_acentos, permitir_reenvio,
                   registros, agendada_para=None):
    """registros: dicts de colunas.registro_da_linha. Sem celular válido ou repetido na planilha já nasce 'ignorado'.
    janela: (hora_inicial, hora_final) ou None. agendada_para: datetime com fuso ou None."""
    ini, fim = janela if janela else (None, None)
    campos = {"nome": nome.strip() or "Campanha SMS", "status": "pendente", "criado_por": usuario, "textos": list(textos),
              "ctx": ctx, "delay_min": float(delay_min), "delay_max": float(delay_max), "janela_ini": ini, "janela_fim": fim,
              "domingo": bool(domingo), "sem_acentos": bool(sem_acentos), "permitir_reenvio": bool(permitir_reenvio),
              "total": len(registros), "atualizado_em": agora_iso()}
    if agendada_para:
        campos["agendada_para"] = agendada_para.astimezone(timezone.utc).isoformat()
    camp = _completar(sb.table("sms_campanhas").insert(campos).execute().data[0])
    sorteio = sms.atribuir_textos(len(registros), textos)
    vistos, linhas = set(), []
    for ordem, reg in enumerate(registros):
        tel = sms.melhor_telefone(reg.get("telefone", ""), reg.get("telefone2", ""))
        chave = f"{reg.get('protocolo', '')}|{sms.normalizar_bloqueio(tel)}"
        motivo = "Sem celular válido" if not tel else ("Repetido na planilha" if chave in vistos else "")
        vistos.add(chave)
        linhas.append({"campanha_id": camp["id"], "ordem": ordem, "protocolo": reg.get("protocolo", ""), "nome": reg.get("nome", ""),
                       "telefone": tel, "email": reg.get("email", ""),
                       "dados": {"_texto": sorteio[ordem] if sorteio else 0},
                       "status": "ignorado" if motivo else "pendente", "detalhe": f"IGNORADO: {motivo}" if motivo else ""})
    for i in range(0, len(linhas), LOTE_INSERCAO):
        sb.table("sms_destinos").insert(linhas[i:i + LOTE_INSERCAO]).execute()
    ign = sum(1 for x in linhas if x["status"] == "ignorado")
    if ign:
        sb.table("sms_campanhas").update({"ignorados": ign}).eq("id", camp["id"]).execute()
        camp["ignorados"] = ign
    return camp


def listar(sb, limite=30):
    return [_completar(c) for c in sb.table("sms_campanhas").select("*").order("id", desc=True).limit(limite).execute().data or []]


def obter(sb, camp_id):
    r = sb.table("sms_campanhas").select("*").eq("id", camp_id).limit(1).execute().data
    return _completar(r[0]) if r else None


def destinos(sb, camp_id, status=None):
    filtros = {"campanha_id": camp_id}
    if status:
        filtros["status"] = status
    return buscar_todos(sb, "sms_destinos", "ordem,protocolo,nome,telefone,status,detalhe,processado_em,dados", filtros, ordem="id")


def protocolos(sb, camp_id):
    return [r["protocolo"] for r in buscar_todos(sb, "sms_destinos", "id,protocolo", {"campanha_id": camp_id}, ordem="id")]


def contagens(sb, camp_id):
    cont = {"pendente": 0, "enviando": 0, "enviado": 0, "erro": 0, "ignorado": 0}
    for r in buscar_todos(sb, "sms_destinos", "id,status", {"campanha_id": camp_id}, ordem="id"):
        cont[r["status"]] = cont.get(r["status"], 0) + 1
    return cont


def tempo_restante_min(camp, pendentes):
    media = (float(camp.get("delay_min") or 20) + float(camp.get("delay_max") or 45)) / 2 + 2
    return round(pendentes * media / 60, 1)


# --- controle (tela)
def _definir_status(sb, camp_id, status, motivo=None, so_se=None):
    q = sb.table("sms_campanhas").update({"status": status, "motivo": motivo, "atualizado_em": agora_iso(),
                                          **({"finalizado_em": agora_iso()} if status in ("concluida", "cancelada") else {})})
    q = q.eq("id", camp_id)
    if so_se:
        q = q.in_("status", list(so_se))
    return q.execute().data


def pausar(sb, camp_id):
    _definir_status(sb, camp_id, "pausada", "Pausada por você.", so_se=STATUS_ATIVOS)


def retomar(sb, camp_id):
    sb.table("sms_campanhas").update({"status": "pendente", "motivo": None, "lease_ate": None, "atualizado_em": agora_iso()}) \
        .eq("id", camp_id).in_("status", ["pausada", "concluida"]).execute()


def cancelar(sb, camp_id):
    _definir_status(sb, camp_id, "cancelada", "Cancelada por você.", so_se=STATUS_ATIVOS + ("pausada",))


def recolocar_erros(sb, camp_id):
    linhas = sb.table("sms_destinos").update({"status": "pendente", "detalhe": ""}) \
        .eq("campanha_id", camp_id).eq("status", "erro").execute().data or []
    if linhas:
        retomar(sb, camp_id)
    return len(linhas)


# --- trabalhador
def candidatas(sb, agora=None):
    """Campanhas ativas cuja hora marcada (se houver) já chegou."""
    todas = sb.table("sms_campanhas").select("*").in_("status", list(STATUS_ATIVOS)).order("id").execute().data or []
    return [c for c in todas if not esta_agendada(c, agora)]


def tem_trabalho(sb, agora=None):
    return bool(candidatas(sb, agora))


def reservar(sb, camp, segundos=180):
    atual = obter(sb, camp["id"])
    if not atual or atual["status"] not in STATUS_ATIVOS:
        return False
    if atual.get("lease_ate") and str(atual["lease_ate"]) > agora_iso():
        return False
    campos = {"status": "rodando", "lease_ate": _em(segundos), "atualizado_em": agora_iso()}
    if not atual.get("iniciado_em"):
        campos["iniciado_em"] = agora_iso()
    return bool(sb.table("sms_campanhas").update(campos).eq("id", camp["id"]).eq("status", atual["status"]).execute().data)


def renovar(sb, camp_id, contadores, segundos=180):
    sb.table("sms_campanhas").update({**contadores, "lease_ate": _em(segundos), "atualizado_em": agora_iso()}).eq("id", camp_id).execute()


def liberar(sb, camp_id, status, motivo=None, contadores=None):
    campos = {"status": status, "motivo": motivo, "lease_ate": None, "atualizado_em": agora_iso(), **(contadores or {})}
    if status == "concluida":
        campos["finalizado_em"] = agora_iso()
    sb.table("sms_campanhas").update(campos).eq("id", camp_id).eq("status", "rodando").execute()
    sb.table("sms_campanhas").update({"lease_ate": None, **(contadores or {})}).eq("id", camp_id).execute()


def proximos(sb, camp_id, quantos):
    return sb.table("sms_destinos").select("*").eq("campanha_id", camp_id).eq("status", "pendente").order("ordem").limit(quantos).execute().data or []


def marcar(sb, ids, status, detalhe=""):
    if ids:
        sb.table("sms_destinos").update({"status": status, "detalhe": detalhe}).in_("id", list(ids)).execute()


def concluir_destino(sb, destino_id, status, detalhe, gateway_id=None, msg_id=""):
    campos = {"status": status, "detalhe": str(detalhe)[:300], "processado_em": agora_iso(), "msg_id": msg_id}
    if gateway_id is not None:
        campos["gateway_id"] = gateway_id
    sb.table("sms_destinos").update(campos).eq("id", destino_id).execute()


def em_andamento(sb, camp_id):
    return sb.table("sms_destinos").select("*").eq("campanha_id", camp_id).eq("status", "enviando").execute().data or []
