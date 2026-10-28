"""Tela 📱 SMS (dentro do Disparador): celulares, envio, fila, lista de SAIR e histórico."""
import re

import pandas as pd
import streamlit as st

from core import auditoria, sessao
from core.config import cfg
from core.exportacao import gerar_excel
from core.utils import agora_br, serie_utc_para_br
from ui.componentes import baixar_excel, cartao, erro_banco, escolher_inicio, metricas, navegacao, vazio

from . import colunas, gatilho, planilha, sms, sms_banco as banco, sms_gateway
from . import repositorio as repo
from .crypto import Cofre

SECOES = ["✉️ Enviar", "⏱️ Fila", "📱 Celulares", "🚫 Sair", "📜 Histórico"]
CAMPOS_SMS = ("protocolo", "nome", "telefone", "telefone2", "email")
ESTADO_ROTULO = {"Delivered": "Entregue", "Sent": "Enviado ao chip", "Failed": "Falhou", "Pending": "Aguardando", "Processed": "Processando"}


def _cofre():
    return Cofre(cfg("CHAVE_CRIPTO"))


def _acordar():
    if not gatilho.configurado(cfg):
        return ("⏳ O trabalhador roda sozinho a cada 30 minutos. Para começar na hora, configure `GITHUB_REPO` e "
                "`GITHUB_TOKEN_DISPARO` nos secrets (veja o README).")
    try:
        gatilho.disparar_pela_tela(cfg, sms=True)
        return "🚀 Trabalhador de SMS acionado: o envio começa em instantes."
    except gatilho.ErroGatilho as erro:
        return f"⚠️ Não consegui acionar na hora ({erro}). Ele roda sozinho no próximo ciclo (até 30 min)."


# ============================================================================ CELULARES
def _passo_a_passo():
    with st.expander("📖 Como ligar o seu celular (faça uma vez)", expanded=False):
        st.markdown(
            "1. No celular Android com o chip, instale o app **SMSGate – SMS Gateway for Android** (gratuito e de código aberto; "
            "o site **sms-gate.app** tem o link de download).\n"
            "2. Abra o app, **permita o envio de SMS** e, em *Configurações*, tire o app da economia de bateria.\n"
            "3. Ligue a chave **Cloud Server** e toque no botão **Offline** até virar **Online**.\n"
            "4. O app mostra o **usuário** e a **senha** da API: cadastre aqui embaixo.\n"
            "5. No app, em *Configurações → Mensagens*, confirme o **intervalo entre mensagens** (ex.: 20 a 45 s), o **limite por hora/dia** e o "
            "**horário de trabalho**. Eles valem junto com os da plataforma.\n"
            "6. Deixe o celular **ligado, com internet e no carregador** enquanto houver SMS na fila.\n\n"
            "Se o aparelho tem dois chips, escolha abaixo qual usar (1 ou 2) ou cadastre o mesmo celular duas vezes, um para cada chip.")
        st.caption("Privacidade: o texto e o número passam pelo servidor do app (conexão segura). O app oferece criptografia de ponta a ponta "
                   "e servidor privado se você quiser mais isolamento.")


def _celulares(sb):
    cofre = _cofre()
    if not cofre.ativo:
        st.warning("🔐 `CHAVE_CRIPTO` não configurada: a senha do app seria salva em texto puro (veja o README).")
    _passo_a_passo()
    with cartao():
        with st.form("sms_form_celular", clear_on_submit=True):
            a, b = st.columns(2)
            nome = a.text_input("Nome do celular (ex.: Chip Vivo 1)")
            url = a.text_input("Endereço da API", value=sms_gateway.URL_NUVEM)
            usuario = b.text_input("Usuário (mostrado no app)")
            senha = b.text_input("Senha (mostrada no app)", type="password")
            c, d = st.columns(2)
            sim = c.selectbox("Chip", ["Padrão do app", "Chip 1", "Chip 2"])
            limite = d.number_input("Limite de SMS por dia neste celular", min_value=10, max_value=1000, value=100)
            if st.form_submit_button("➕ Salvar celular", type="primary"):
                if not (nome.strip() and usuario.strip() and senha.strip()):
                    st.warning("Preencha nome, usuário e senha.")
                else:
                    try:
                        banco.criar_gateway(sb, cofre, nome, url, usuario, senha, {"Chip 1": 1, "Chip 2": 2}.get(sim), limite)
                        auditoria.registrar(sb, sessao.usuario_atual()["usuario"], "sms_celular_cadastrado", nome)
                        st.success(f"✅ Celular {nome} cadastrado. Use **Testar conexão** abaixo.")
                        st.rerun()
                    except Exception as erro:  # noqa: BLE001
                        st.error(f"Erro ao salvar (rodou o `migracao_v7.sql`?): {erro}")
    try:
        celulares = banco.listar_gateways(sb)
        usados = banco.enviados_hoje(sb)
    except Exception as erro:  # noqa: BLE001
        st.error(f"Erro ao listar celulares (rodou o `migracao_v7.sql`?): {erro}")
        return
    if not celulares:
        vazio("Nenhum celular cadastrado ainda.")
        return
    for g in celulares:
        c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 2])
        c1.write(f"📱 **{g['nome']}** · {g.get('usuario')}" + (f" · chip {g['sim_numero']}" if g.get("sim_numero") else ""))
        c2.write(f"Hoje: {usados.get(g['id'], 0)}/{g['limite_diario']}")
        c3.write("🟢 Ativo" if g["ativo"] else "🔴 Inativo")
        if c4.button("Desativar" if g["ativo"] else "Ativar", key=f"sms_tog_{g['id']}"):
            banco.alternar_gateway(sb, g["id"], not g["ativo"])
            st.rerun()
        if c5.button("🔌 Testar conexão", key=f"sms_test_{g['id']}"):
            cliente = sms_gateway.criar(g, cofre)
            if cliente is None:
                st.error("Senha ilegível (confira a CHAVE_CRIPTO).")
            else:
                ok, texto = cliente.testar()
                (st.success if ok else st.error)(texto)
        with st.expander(f"⚙️ Mais opções de {g['nome']}"):
            novo = st.number_input("Limite por dia", min_value=10, max_value=1000, value=int(g["limite_diario"]), key=f"sms_lim_{g['id']}")
            x, y = st.columns(2)
            if x.button("Salvar limite", key=f"sms_savelim_{g['id']}"):
                banco.mudar_limite_gateway(sb, g["id"], novo)
                st.rerun()
            if st.checkbox("Confirmo que quero remover este celular", key=f"sms_rmok_{g['id']}") and y.button(
                    "🗑️ Remover celular", key=f"sms_rm_{g['id']}"):
                banco.remover_gateway(sb, g["id"])
                st.rerun()


# ============================================================================== ENVIAR
def _mapa_colunas(df):
    detectadas = colunas.detectar_colunas(df)
    opcoes = ["(nenhuma)"] + list(df.columns)
    sufixo = hash(tuple(df.columns)) & 0xffff
    mapa = {}
    with st.expander("🧩 Colunas reconhecidas na planilha" + ("" if detectadas.get("telefone") else "  ⚠️ confira o telefone"),
                     expanded=not detectadas.get("telefone")):
        cols = st.columns(len(CAMPOS_SMS))
        for i, campo in enumerate(CAMPOS_SMS):
            atual = detectadas.get(campo)
            escolhido = cols[i].selectbox(colunas.ROTULOS[campo], opcoes, index=opcoes.index(atual) if atual in opcoes else 0,
                                          key=f"sms_map_{campo}_{sufixo}")
            mapa[campo] = None if escolhido == "(nenhuma)" else escolhido
    return mapa


def _escolher_textos():
    """Devolve a lista de textos (modelos) escolhidos: prontos + até 3 seus."""
    nomes = [m["nome"] for m in sms.MODELOS_PADRAO]
    marcados = st.multiselect("Textos (quanto mais variações, menos o SMS parece em massa)", nomes, default=nomes[:3], key="sms_textos")
    textos = [m["texto"] for m in sms.MODELOS_PADRAO if m["nome"] in marcados]
    with st.expander("✍️ Escrever o meu próprio texto"):
        st.caption("Campos: {nome} (primeiro nome), {protocolo}, {empresa}, {link} (conversa no WhatsApp) e {sair} (frase de saída).")
        for i in range(1, 4):
            proprio = st.text_area(f"Meu texto {i}", key=f"sms_proprio_{i}", height=70).strip()
            if proprio:
                textos.append(proprio)
    return textos


def _previa(textos, registro, ctx, sem_acentos):
    with st.expander("👁️ Pré-visualizar o SMS", expanded=True):
        for i, modelo in enumerate(textos, 1):
            texto = sms.montar_texto(modelo, registro, ctx, sem_acentos)
            n, partes, cod = sms.partes(texto)
            st.code(texto, language=None)
            st.caption(f"Texto {i}: {n} caracteres · {partes} SMS ({cod})")
            for aviso in sms.avisos_do_texto(texto):
                st.warning(aviso)


def _teste(gateways, texto_exemplo, ctx, sem_acentos, cofre):
    st.markdown("##### 🧪 SMS de teste")
    numero = st.text_input("Seu celular para receber o teste (com DDD)", key="sms_teste_numero")
    escolhido = st.selectbox("Enviar pelo celular", [g["nome"] for g in gateways], key="sms_teste_gateway")
    if st.button("📲 Enviar SMS de teste", key="sms_teste_btn"):
        tel = sms.telefone_e164(numero)
        if not tel:
            st.warning("Informe um celular válido com DDD (ex.: 11 98765-4321).")
            return
        g = next(x for x in gateways if x["nome"] == escolhido)
        cliente = sms_gateway.criar(g, cofre)
        texto = sms.montar_texto(texto_exemplo, {"nome": "Teste", "protocolo": "TESTE"}, ctx, sem_acentos)
        try:
            id_msg, estado = cliente.enviar(tel, texto)
            st.success(f"✅ Entregue ao app ({estado}). O SMS deve chegar em instantes em {tel}.")
        except sms_gateway.ErroGateway as erro:
            st.error(f"Não saiu: {erro}")


def _pagina_enviar(sb):
    empresa = cfg("EMPRESA_NOME")
    if not empresa:
        st.error("Defina `EMPRESA_NOME` nos secrets antes de enviar: quem recebe precisa saber quem está falando.")
        return
    cofre = _cofre()
    try:
        gateways, sem_senha = banco.carregar_gateways_ativos(sb, cofre)
        usados = banco.enviados_hoje(sb)
    except Exception as erro:  # noqa: BLE001
        st.error(f"Não consegui ler os celulares (rodou o `migracao_v7.sql`?): {erro}")
        return
    if sem_senha:
        st.warning("⚠️ Celulares ignorados por senha ilegível (confira a CHAVE_CRIPTO): " + ", ".join(g["nome"] for g in sem_senha))
    if not gateways:
        st.warning("⚠️ Nenhum celular ativo. Cadastre em **📱 Celulares**.")
        return
    capacidade = sum(max(0, int(g.get("limite_diario") or 0) - usados.get(g["id"], 0)) for g in gateways)
    metricas([("📱 Celulares ativos", len(gateways)), ("📤 Enviados hoje", sum(usados.values())), ("🔋 Capacidade restante hoje", capacidade)])

    arquivo = st.file_uploader("📂 1 · Planilha (.xlsx, .xls, .csv ou .txt) com o telefone dos clientes",
                               type=["xlsx", "xls", "csv", "txt"], key="sms_planilha")
    if not arquivo:
        return
    chave_arq = f"{arquivo.name}:{arquivo.size}"
    if st.session_state.get("sms_planilha_chave") != chave_arq:
        try:
            st.session_state["sms_planilha_df"] = planilha.limpar_dataframe(planilha.carregar_dataframe(arquivo))
            st.session_state["sms_planilha_chave"] = chave_arq
        except Exception as erro:  # noqa: BLE001
            st.error(f"Erro ao ler o arquivo: {erro}")
            return
    df = st.session_state["sms_planilha_df"]
    if df.empty:
        st.error("A planilha está vazia.")
        return
    mapa = _mapa_colunas(df)
    if not mapa.get("telefone"):
        st.error("Escolha qual coluna contém o **telefone/celular**.")
        return
    registros = [colunas.registro_da_linha(linha, mapa) for _, linha in df.iterrows()]

    st.markdown("#### 2 · Texto")
    textos = _escolher_textos()
    if not textos:
        st.info("Escolha ao menos um texto.")
        return
    numero_whats = re.sub(r"\D", "", st.text_input("WhatsApp da empresa para o link (DDI+DDD+número)", value=str(cfg("WHATSAPP_NUMERO")),
                                                   key="sms_whats"))
    if not numero_whats:
        st.warning("Informe o WhatsApp de destino (ou defina `WHATSAPP_NUMERO` nos secrets): é o link que o cliente vai tocar.")
        return
    ctx = {"empresa": str(empresa), "num_whatsapp": numero_whats}
    sem_acentos = st.checkbox("Tirar acentos (recomendado: cabe mais texto por SMS)", value=True, key="sms_sem_acentos")
    exemplo = next((r for r in registros if sms.melhor_telefone(r.get("telefone"), r.get("telefone2"))), registros[0])
    _previa(textos, exemplo, ctx, sem_acentos)

    st.markdown("#### 3 · Ritmo e horário")
    a, b, c = st.columns(3)
    delay_min = a.number_input("Intervalo mínimo entre SMS (s)", min_value=5, max_value=600, value=20, key="sms_dmin")
    delay_max = b.number_input("Intervalo máximo entre SMS (s)", min_value=5, max_value=900, value=45, key="sms_dmax")
    reenvio = c.checkbox("Permitir reenviar para quem já recebeu", value=False, key="sms_reenvio")
    d, e, f = st.columns(3)
    h_ini = d.number_input("Enviar a partir das (hora)", min_value=0, max_value=23, value=9, key="sms_hini")
    h_fim = e.number_input("Enviar até as (hora)", min_value=1, max_value=24, value=19, key="sms_hfim")
    domingo = f.checkbox("Enviar também aos domingos", value=False, key="sms_domingo")
    st.caption("Recomendação do mercado: mensagens comerciais só em horário comercial e fora de domingo, no máximo 2 a 3 por pessoa por semana.")
    inicio = escolher_inicio("sms_inicio")

    st.markdown("#### 4 · Quem vai receber")
    try:
        bloqueados = banco.telefones_descadastrados(sb)
        emails_sair = repo.emails_descadastrados(sb)
        ja = banco.ja_enviados(sb, [r["protocolo"] for r in registros])
    except Exception as erro:  # noqa: BLE001
        erro_banco(erro)
        return
    contagem = {"vao": 0, "sem_celular": 0, "sair": 0, "ja": 0, "repetido": 0}
    vistos = set()
    for r in registros:
        tel = sms.melhor_telefone(r.get("telefone"), r.get("telefone2"))
        chave = f"{r['protocolo']}|{sms.normalizar_bloqueio(tel)}"
        if tel and chave in vistos:
            contagem["repetido"] += 1
            continue
        vistos.add(chave)
        motivo = sms.triar(tel, bloqueados, ja, reenvio, r["protocolo"], r["email"], emails_sair)
        if not motivo:
            contagem["vao"] += 1
        elif motivo.startswith("Sem celular"):
            contagem["sem_celular"] += 1
        elif motivo.startswith("Pediu"):
            contagem["sair"] += 1
        else:
            contagem["ja"] += 1
    metricas([("📋 Na planilha", len(registros)), ("✅ Vão receber", contagem["vao"]), ("📵 Sem celular", contagem["sem_celular"]),
              ("🚫 Pediram para sair", contagem["sair"]), ("🔁 Já receberam", contagem["ja"])])
    if contagem["vao"] > capacidade:
        st.info(f"A capacidade de hoje ({capacidade}) é menor que {contagem['vao']}: o envio para no limite e continua no dia seguinte.")
    if contagem["vao"] > 100:
        st.warning("Para os primeiros envios, comece com poucos (até ~100 por dia) e veja se chegam e se as pessoas respondem.")

    _teste(gateways, textos[0], ctx, sem_acentos, cofre)

    st.markdown("#### 5 · Colocar na fila")
    revisado = st.checkbox(f"✅ Revisei os textos, fiz o teste e quero enviar para {contagem['vao']} pessoa(s)", key="sms_revisado")
    nome_campanha = st.text_input("Nome da campanha", value=f"SMS · {agora_br():%d/%m %H:%M}", key="sms_nome_campanha")
    if h_fim <= h_ini:
        st.warning("A hora final precisa ser maior que a inicial.")
    if st.button("📥 Colocar na fila", type="primary", key="sms_fila_btn",
                 disabled=not (revisado and contagem["vao"] and h_fim > h_ini)):
        usuario = sessao.usuario_atual()["usuario"]
        try:
            camp = banco.criar_campanha(sb, usuario, nome_campanha, textos, ctx, delay_min, delay_max, (int(h_ini), int(h_fim)), domingo,
                                        sem_acentos, reenvio, registros, agendada_para=inicio)
        except Exception as erro:  # noqa: BLE001
            st.error(f"Não foi possível criar a fila (rodou o `migracao_v7.sql`?): {erro}")
            return
        auditoria.registrar(sb, usuario, "sms_campanha_na_fila", f"#{camp['id']} {camp['nome']} ({len(registros)} linhas)")
        st.success(f"✅ Campanha **#{camp['id']}** na fila. Abra **⏱️ Fila** para acompanhar.")
        st.info(_acordar() if not inicio else "🕘 Agendada: o trabalhador começa quando chegar a hora marcada.")


# ================================================================================ FILA
def _cartao(sb, c):
    feitos = c["enviados"] + c["erros"] + c["ignorados"]
    restam = max(c["total"] - feitos, 0)
    ativo = c["status"] in banco.STATUS_ATIVOS
    with st.expander(f"{banco.rotulo(c)} · #{c['id']} · {c['nome']}", expanded=ativo or c["status"] == "pausada"):
        st.progress(min(feitos / max(c["total"], 1), 1.0))
        metricas([("✅ Enviados", c["enviados"]), ("❌ Erros", c["erros"]), ("⏭️ Pulados", c["ignorados"]),
                  ("⏳ Faltam", restam, f"≈ {banco.tempo_restante_min(c, restam)} min só de intervalo" if ativo and restam else None)])
        if c.get("motivo"):
            st.warning(c["motivo"])
        if banco.esta_agendada(c):
            quando = serie_utc_para_br(pd.Series([c["agendada_para"]])).iloc[0]
            st.info(f"🕘 Começa em {quando}.")
        horario = f"{c['janela_ini']}h às {c['janela_fim']}h" if c.get("janela_ini") is not None else "qualquer hora"
        st.caption(f"Horário: {horario}{' (inclui domingo)' if c.get('domingo') else ''} · intervalo {int(float(c['delay_min']))}"
                   f"–{int(float(c['delay_max']))} s · criada por {c.get('criado_por') or '—'}")
        b = st.columns(4)
        if ativo and b[0].button("⏸️ Pausar", key=f"sms_p_{c['id']}"):
            banco.pausar(sb, c["id"])
            st.rerun()
        if c["status"] == "pausada" and b[0].button("▶️ Retomar", key=f"sms_r_{c['id']}", type="primary"):
            banco.retomar(sb, c["id"])
            st.info(_acordar())
        if c["status"] in banco.STATUS_ATIVOS + ("pausada",) and b[1].button("🛑 Cancelar", key=f"sms_c_{c['id']}"):
            banco.cancelar(sb, c["id"])
            st.rerun()
        if c["erros"] and c["status"] != "cancelada" and b[2].button("↻ Reenviar os erros", key=f"sms_e_{c['id']}"):
            st.info(f"{banco.recolocar_erros(sb, c['id'])} SMS voltaram para a fila. " + _acordar())
        if b[3].button("📊 Preparar relatório", key=f"sms_x_{c['id']}"):
            linhas = banco.destinos(sb, c["id"])
            tabela = pd.DataFrame([{"Protocolo": d["protocolo"], "Nome": d["nome"], "Telefone": d["telefone"], "Situação": d["status"],
                                    "Detalhe": d["detalhe"], "Processado em": d["processado_em"]} for d in linhas])
            st.session_state[f"sms_rel_{c['id']}"] = gerar_excel({"SMS": tabela})
        if st.session_state.get(f"sms_rel_{c['id']}"):
            baixar_excel("⬇️ Baixar relatório", st.session_state[f"sms_rel_{c['id']}"], f"sms_campanha_{c['id']}.xlsx", chave=f"sms_dl_{c['id']}")


def _pagina_fila(sb):
    st.caption("O trabalhador entrega os SMS ao app do seu celular, no ritmo e no horário escolhidos. O celular precisa estar ligado e com internet.")
    a, b = st.columns(2)
    a.button("🔄 Atualizar", key="sms_atualizar", use_container_width=True)
    if b.button("🚀 Acionar trabalhador agora", key="sms_acordar", use_container_width=True):
        st.info(_acordar())
    try:
        campanhas = banco.listar(sb)
    except Exception as erro:  # noqa: BLE001
        st.error(f"Não foi possível ler a fila (rodou o `migracao_v7.sql`?): {erro}")
        return
    if not campanhas:
        vazio("Nenhuma campanha de SMS ainda. Use **✉️ Enviar**.")
        return
    for c in campanhas:
        _cartao(sb, c)


# ================================================================================ SAIR
def _pagina_sair(sb):
    st.caption("Quem responder **SAIR** (ou pedir para não receber) entra aqui e nunca mais recebe SMS. Cole os números dos pedidos.")
    texto = st.text_area("Telefones (um por linha ou separados por vírgula)", height=100, key="sms_sair_txt")
    if st.button("➕ Adicionar à lista", type="primary", key="sms_sair_add"):
        numeros = re.split(r"[\n,;]+", texto)
        try:
            n = banco.adicionar_descadastros(sb, numeros)
        except Exception as erro:  # noqa: BLE001
            st.error(f"Erro ao salvar (rodou o `migracao_v7.sql`?): {erro}")
            return
        if n:
            st.success(f"✅ {n} número(s) adicionados.")
            st.rerun()
        else:
            st.warning("Nenhum número válido encontrado.")
    try:
        lista = banco.listar_descadastros(sb)
    except Exception as erro:  # noqa: BLE001
        st.error(f"Erro ao listar: {erro}")
        return
    st.write(f"Total na lista: **{len(lista)}**")
    filtro = re.sub(r"\D", "", st.text_input("Buscar número", key="sms_sair_busca"))
    for r in [x for x in lista if filtro in x["telefone"]][:100]:
        c1, c2 = st.columns([5, 1])
        c1.write(f"+{r['telefone']}")
        if c2.button("Remover", key=f"sms_sair_rm_{r['telefone']}"):
            banco.remover_descadastro(sb, r["telefone"])
            st.rerun()


# ============================================================================ HISTÓRICO
def _pagina_historico(sb):
    a, b = st.columns([1, 2])
    limite = a.selectbox("Quantos mostrar", [200, 500, 2000], index=1, key="sms_hist_lim")
    if b.button("🔄 Conferir entrega dos últimos 100 SMS", key="sms_conferir",
                help="Pergunta ao app do celular se cada SMS foi entregue ou falhou (pode levar alguns segundos)."):
        try:
            cont = banco.atualizar_estados(sb, _cofre(), 100)
            st.success("Conferido: " + (", ".join(f"{ESTADO_ROTULO.get(k, k)} {v}" for k, v in cont.items()) or "nada novo para conferir."))
        except ValueError as erro:
            st.error(str(erro))
        except Exception as erro:  # noqa: BLE001
            st.error(f"Não consegui conferir agora: {erro}")
    try:
        linhas = banco.historico(sb, limite)
    except Exception as erro:  # noqa: BLE001
        st.error(f"Erro ao ler o histórico (rodou o `migracao_v7.sql`?): {erro}")
        return
    if not linhas:
        vazio("Nenhum SMS enviado ainda.")
        return
    df = pd.DataFrame(linhas)
    df["data_hora"] = serie_utc_para_br(df["data_hora"])
    if "estado" in df.columns:
        df["estado"] = df["estado"].map(lambda e: ESTADO_ROTULO.get(e, e or ""))
    itens = [("✅ Enviados", int((df["status"] == "enviado").sum())), ("❌ Erros", int((df["status"] == "erro").sum()))]
    if "estado" in df.columns:
        itens += [("📬 Entregues", int((df["estado"] == ESTADO_ROTULO["Delivered"]).sum())),
                  ("⚠️ Falharam no celular", int((df["estado"] == ESTADO_ROTULO["Failed"]).sum()))]
    metricas(itens)
    st.dataframe(df, hide_index=True, use_container_width=True)
    baixar_excel("📊 Baixar histórico (.xlsx)", gerar_excel({"SMS": df}), "historico_sms.xlsx", chave="sms_baixar_hist")


# ================================================================================ ENTRADA
def renderizar_sms(sb):
    secao = navegacao(SECOES, "nav_sms")
    {"✉️ Enviar": _pagina_enviar, "⏱️ Fila": _pagina_fila, "📱 Celulares": _celulares, "🚫 Sair": _pagina_sair,
     "📜 Histórico": _pagina_historico}[secao](sb)
