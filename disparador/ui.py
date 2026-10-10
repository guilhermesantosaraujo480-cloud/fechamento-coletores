"""Interface do disparador de e-mails (única parte do pacote que usa Streamlit)."""
import re

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.config import cfg
from core.consulta import buscar_todos, contar
from core.exportacao import gerar_excel
from core.utils import agora_br, serie_utc_para_br
from ui.componentes import baixar_excel, cabecalho, cartao, erro_banco, metricas, navegacao, vazio

from . import campanha, colunas, ia, planilha, templates
from . import metricas as met
from . import repositorio as repo
from .crypto import Cofre
from .envio_smtp import GerenteSMTP
from .utils import email_valido, separar_emails

SECOES = ["🚀 Disparos", "✉️ Modelos", "🔑 Contas", "🚫 Descadastros", "📜 Histórico", "📈 Cliques"]


def _cofre():
    return Cofre(cfg("CHAVE_CRIPTO"))


@st.cache_data(ttl=60, show_spinner=False)
def _listas_de_bloqueio(_sb):
    return repo.emails_descadastrados(_sb), repo.ja_enviados(_sb)


# =========================================================================== DISPAROS
def _mostrar_ultimo_disparo():
    ultimo = st.session_state.get("ultimo_disparo")
    if not ultimo:
        return
    resumo, df = ultimo["resumo"], ultimo["df"]
    with cartao():
        st.markdown(f"**🧾 Último disparo** · {ultimo['hora']}")
        metricas([("✅ Enviados", resumo.sucessos), ("⏭️ Ignorados", resumo.ignorados), ("❌ Erros", resumo.erros),
                  ("⏳ Não processados", resumo.total - len(resumo.resultado))])
        if resumo.motivo_parada:
            st.warning(resumo.motivo_parada)
        for aviso in resumo.avisos:
            st.warning(aviso)
        if resumo.falhas_log:
            st.warning(f"{resumo.falhas_log} envio(s) não foram gravados no histórico (tabela envios_email). "
                       "Esses clientes podem receber de novo numa próxima rodada.")
        saida = df.copy()
        saida["status_envio"] = [resumo.resultado.get(i, ("NÃO PROCESSADO", ""))[0] for i in range(len(saida))]
        saida["data_hora"] = [resumo.resultado.get(i, ("", ""))[1] for i in range(len(saida))]
        baixar_excel("📊 Baixar relatório do disparo (.xlsx)", gerar_excel({"Resultado": saida}),
                     f"relatorio_disparos_{agora_br():%Y%m%d_%H%M%S}.xlsx", chave="baixar_ultimo_disparo")


def _escolher_colunas(df, detectadas):
    """Mostra o que foi reconhecido e deixa corrigir. Devolve o mapa final."""
    faltando = [c for c in colunas.OBRIGATORIOS if not detectadas.get(c)]
    with st.expander("🧩 Colunas reconhecidas na planilha" + ("  ⚠️ confira" if faltando else "  ✅"), expanded=bool(faltando)):
        opcoes = ["(nenhuma)"] + list(df.columns)
        mapa = {}
        cols = st.columns(4)
        for i, campo in enumerate(colunas.CAMPOS):
            atual = detectadas.get(campo)
            mapa[campo] = cols[i % 4].selectbox(colunas.ROTULOS[campo], opcoes,
                                                index=opcoes.index(atual) if atual in opcoes else 0,
                                                key=f"map_{campo}_{hash(tuple(df.columns)) & 0xffff}")
            if mapa[campo] == "(nenhuma)":
                mapa[campo] = None
    return mapa


def _modelos_disponiveis(sb):
    opcoes = {
        "[Padrão 1] Cancelamento (voluntário/involuntário)": {"tipo": "padrao1"},
        "[Padrão 2] Comunicado de rota técnica": {"tipo": "padrao2"},
    }
    try:
        for m in repo.listar_modelos(sb, somente_ativos=True):
            opcoes[f"[Salvo] {m['nome']}"] = {"tipo": "db", **m}
    except Exception:
        st.caption("ℹ️ Modelos salvos indisponíveis (rode o `migracao.sql`).")
    return opcoes


def _teste(contas, dados_previa, empresa):
    c1, c2 = st.columns([3, 1])
    email_teste = c1.text_input("E-mail para teste", placeholder="seu@email.com", key="email_teste").strip().lower()
    if c2.button("📨 Enviar teste", use_container_width=True):
        if not email_valido(email_teste):
            st.error("Informe um e-mail de teste válido.")
            return
        gerente = GerenteSMTP()
        try:
            gerente.enviar(contas[0], templates.construir_mensagem(contas[0], email_teste, dados_previa, empresa))
            st.success(f"✅ Teste enviado para {email_teste} via {contas[0]['email']}. Confira também o spam.")
        except Exception as erro:
            st.error(f"Falha no teste: {erro}")
        finally:
            gerente.fechar()


def _executar(sb, df, mapa, contas, enviados_hoje, params):
    try:  # lista fresca (sem cache): descadastros e histórico precisam estar atualizados na hora do envio
        descadastrados, ja_enviados = repo.emails_descadastrados(sb), repo.ja_enviados(sb)
    except Exception as erro:
        st.error(f"Não foi possível consultar descadastros/histórico (rodou o SQL de migração?): {erro}")
        return
    barra, texto = st.progress(0.0), st.empty()
    gerente = GerenteSMTP()

    def progresso(feitos, resumo):
        barra.progress(min(feitos / max(resumo.total, 1), 1.0))
        texto.text(f"Processando {feitos}/{resumo.total} · enviados {resumo.sucessos} · erros {resumo.erros}")
        st.session_state["ultimo_disparo"] = {"df": df, "resumo": resumo, "hora": agora_br().strftime("%d/%m/%Y %H:%M")}

    try:
        resumo = campanha.executar_campanha(
            df, mapa, contas, enviados_hoje, descadastrados, ja_enviados, gerente, params,
            registrar=lambda *a: repo.registrar_envio(sb, *a), progresso=progresso,
            parar=lambda: st.session_state.get("parar_disparo", False))
    finally:
        gerente.fechar()
    st.session_state["ultimo_disparo"] = {"df": df, "resumo": resumo, "hora": agora_br().strftime("%d/%m/%Y %H:%M")}
    _listas_de_bloqueio.clear()
    st.rerun()


def _pagina_disparo(sb):
    empresa = cfg("EMPRESA_NOME")
    if not empresa:
        st.error("Defina `EMPRESA_NOME` (e `EMPRESA_IDENTIFICACAO`, ex.: CNPJ e contato) nos secrets antes de disparar. "
                 "O destinatário precisa saber quem está enviando.")
        return
    try:
        contas, sem_senha = repo.carregar_contas_ativas(sb, _cofre())
        enviados_hoje = repo.contar_enviados_hoje(sb)
    except Exception as erro:
        erro_banco(erro)
        return
    if sem_senha:
        st.warning("⚠️ Contas ignoradas por senha ilegível (confira a CHAVE_CRIPTO nos secrets): "
                   + ", ".join(c["email"] for c in sem_senha))
    if not contas:
        st.warning("⚠️ Nenhuma conta de e-mail ativa. Cadastre e ative uma na seção **Contas**.")
        return
    capacidade = sum(max(0, int(c.get("limite_diario") or 0) - enviados_hoje.get(c["email"], 0)) for c in contas)
    metricas([("📧 Contas ativas", len(contas)), ("📤 Enviados hoje", sum(enviados_hoje.values())),
              ("🔋 Capacidade restante hoje", capacidade)])
    _mostrar_ultimo_disparo()

    # ---- 1. planilha
    arquivo = st.file_uploader("📂 1 · Planilha de clientes (.xlsx, .xls, .csv ou .txt)", type=["xlsx", "xls", "csv", "txt"])
    if not arquivo:
        return
    chave_arq = f"{arquivo.name}:{arquivo.size}"
    if st.session_state.get("planilha_chave") != chave_arq:
        try:
            st.session_state["planilha_df"] = planilha.limpar_dataframe(planilha.carregar_dataframe(arquivo))
            st.session_state["planilha_chave"] = chave_arq
        except Exception as erro:
            st.error(f"Erro ao ler o arquivo: {erro}")
            return
    df = st.session_state["planilha_df"]
    if df.empty:
        st.error("A planilha está vazia.")
        return
    st.success(f"📋 {len(df)} registros carregados.")
    mapa = _escolher_colunas(df, colunas.detectar_colunas(df))
    if not mapa.get("email"):
        st.error("Escolha qual coluna contém o **e-mail** para continuar.")
        return

    # ---- 2. campanha
    st.markdown("#### 2 · Configuração")
    opcoes = _modelos_disponiveis(sb)
    c1, c2 = st.columns(2)
    with c1:
        nome_modelo = st.selectbox("Modelo do e-mail", list(opcoes))
        whatsapp = st.text_input("WhatsApp de destino (DDI+DDD+número)", value=str(cfg("WHATSAPP_NUMERO")))
    with c2:
        delay_min = st.number_input("Intervalo mínimo entre envios (s)", min_value=1, max_value=60, value=4)
        delay_max = st.number_input("Intervalo máximo entre envios (s)", min_value=1, max_value=60, value=8)
        reenvio = st.checkbox("Permitir reenviar para quem já recebeu", value=False)
    numero = re.sub(r"\D", "", whatsapp)
    if not numero:
        st.warning("Informe o WhatsApp de destino (ou defina `WHATSAPP_NUMERO` nos secrets).")
        return
    if not cfg("URL_FUNCAO_CLIQUE"):
        st.caption("ℹ️ `URL_FUNCAO_CLIQUE` não definida: o botão abrirá o WhatsApp direto, sem contar cliques.")
    ctx = {"empresa": empresa, "identificacao": str(cfg("EMPRESA_IDENTIFICACAO")), "valor_multa": str(cfg("VALOR_MULTA")),
           "url_clique": str(cfg("URL_FUNCAO_CLIQUE")), "num_whatsapp": numero}
    params = campanha.Parametros(opcoes[nome_modelo], nome_modelo, ctx, delay_min, delay_max, reenvio)

    # ---- 3. relatório pré-envio
    st.markdown("#### 3 · Quem vai receber")
    try:
        descadastrados, ja_enviados = _listas_de_bloqueio(sb)
    except Exception as erro:
        st.error(f"Não foi possível consultar descadastros/histórico (rodou o SQL de migração?): {erro}")
        return
    rel = planilha.relatorio_previo(df, mapa, descadastrados, ja_enviados, reenvio)
    metricas([("📋 Na planilha", rel.total), ("✅ Vão receber", rel.enviaveis),
              ("⏭️ Serão pulados", rel.total - rel.enviaveis)])
    if rel.motivos:
        with st.expander("Ver motivos dos pulados"):
            for motivo, qtd in sorted(rel.motivos.items(), key=lambda x: -x[1]):
                st.write(f"{qtd} × {motivo.replace('IGNORADO: ', '')}")
    if rel.enviaveis > capacidade:
        st.info(f"Capacidade de hoje ({capacidade}) é menor que {rel.enviaveis}. O disparo para sozinho no limite; "
                "continue amanhã com a mesma planilha (quem já recebeu é pulado).")

    # ---- 4. prévia e teste
    st.markdown("#### 4 · Prévia e teste")
    registros = (colunas.registro_da_linha(linha, mapa) for _, linha in df.head(200).iterrows())
    primeiro = next((r for r in registros if email_valido(r["email"])), None)
    if primeiro is None:
        st.error("Nenhum e-mail válido nas primeiras linhas da planilha.")
        return
    dados_previa = templates.preparar_dados(primeiro, params.modelo, ctx, "previa")
    with st.expander("👁️ Pré-visualizar o e-mail"):
        st.caption(f"Assunto: {dados_previa['assunto']}")
        components.html(dados_previa["html"], height=720, scrolling=True)
    _teste(contas, dados_previa, empresa)

    # ---- 5. disparo
    st.markdown("#### 5 · Disparar")
    revisado = st.checkbox(f"✅ Revisei a prévia, recebi o teste e quero enviar para {rel.enviaveis} pessoa(s)")
    b1, b2 = st.columns([3, 1])
    if b2.button("🛑 PARAR", use_container_width=True):
        st.session_state["parar_disparo"] = True
    if b1.button("🚀 Iniciar disparos", type="primary", use_container_width=True, disabled=not (revisado and rel.enviaveis)):
        st.session_state["parar_disparo"] = False
        _executar(sb, df, mapa, contas, enviados_hoje, params)


# =========================================================================== MODELOS
def _formulario_modelo(sb, chave, assunto_ini="", texto_ini=""):
    nome = st.text_input("Nome do modelo", key=f"mn_{chave}")
    assunto = st.text_input("Assunto", value=assunto_ini, key=f"ma_{chave}")
    texto = st.text_area("Texto (use {nome}, {protocolo}, {endereco})", value=texto_ini, height=160, key=f"mt_{chave}")
    regras = st.text_area("Informações importantes (caixa cinza do e-mail)", value=templates.REGRAS_PADRAO, height=80, key=f"mr_{chave}")
    for aviso in ia.avisos_do_modelo(assunto, texto):
        st.warning("⚠️ " + aviso)
    if st.button("💾 Salvar modelo", key=f"ms_{chave}", type="primary"):
        if not (nome.strip() and assunto.strip() and texto.strip()):
            st.error("Preencha nome, assunto e texto.")
            return
        try:
            repo.salvar_modelo(sb, nome, assunto, texto, regras)
            st.success("✅ Modelo salvo! Ele já aparece na seção Disparos.")
        except Exception as erro:
            st.error(f"Erro ao salvar (a tabela modelos_email existe?): {erro}")


def _pagina_modelos(sb):
    st.caption("A IA só cria **rascunhos**. Você revisa, edita e salva; o disparo usa apenas modelos aprovados por você.")
    chave = cfg("GEMINI_API_KEY")
    if not chave:
        st.info("Para usar a IA, crie uma chave grátis em aistudio.google.com e coloque `GEMINI_API_KEY` nos secrets. "
                "Enquanto isso, escreva modelos manualmente abaixo.")
    else:
        with cartao():
            with st.form("form_ia"):
                situacao = st.text_area("Descreva a situação", height=90,
                                        placeholder="Ex.: cliente cancelou o plano e precisa devolver o modem; peça para confirmar o endereço pelo WhatsApp.")
                c1, c2 = st.columns(2)
                tom = c1.selectbox("Tom", ["Educado e objetivo", "Amigável", "Formal", "Firme, porém respeitoso"])
                qtd = c2.number_input("Variações", min_value=1, max_value=5, value=3)
                gerar = st.form_submit_button("✨ Gerar rascunhos", type="primary")
            if gerar:
                if not situacao.strip():
                    st.warning("Descreva a situação.")
                else:
                    try:
                        with st.spinner("Gerando..."):
                            st.session_state["ia_resultados"] = ia.gerar_modelos_ia(
                                chave, cfg("GEMINI_MODEL", ia.MODELO_PADRAO), situacao.strip(), tom, int(qtd))
                        st.session_state["ia_lote"] = st.session_state.get("ia_lote", 0) + 1
                    except ia.ErroIA as erro:
                        st.error(str(erro))
            if st.button("🔎 Ver modelos disponíveis na minha chave"):
                try:
                    st.code("\n".join(ia.listar_modelos_gemini(chave)), language="text")
                    st.caption("Copie um nome (ex.: gemini-2.0-flash) para `GEMINI_MODEL` nos secrets.")
                except ia.ErroIA as erro:
                    st.error(str(erro))

    for i, item in enumerate(st.session_state.get("ia_resultados", [])):
        with st.expander(f"Rascunho {i + 1}: {item['assunto'][:60]}", expanded=(i == 0)):
            _formulario_modelo(sb, f"ia_{st.session_state.get('ia_lote', 0)}_{i}", item["assunto"], item["texto"])
    with st.expander("✍️ Escrever modelo manualmente"):
        _formulario_modelo(sb, "manual")

    st.markdown("##### Modelos salvos")
    try:
        modelos = repo.listar_modelos(sb)
    except Exception as erro:
        st.error(f"Erro ao listar modelos (a tabela modelos_email existe?): {erro}")
        return
    if not modelos:
        vazio("Nenhum modelo salvo ainda.")
    for m in modelos:
        c1, c2, c3 = st.columns([5, 1.3, 1])
        c1.write(f"{'🟢' if m['ativo'] else '🔴'} **{m['nome']}** — {m['assunto']}")
        if c2.button("Ativar/Desativar", key=f"mtog_{m['id']}"):
            repo.alternar_modelo(sb, m["id"], not m["ativo"])
            st.rerun()
        if c3.button("Excluir", key=f"mdel_{m['id']}"):
            repo.excluir_modelo(sb, m["id"])
            st.rerun()


# =========================================================================== CONTAS
def _pagina_contas(sb):
    cofre = _cofre()
    if not cofre.ativo:
        st.warning("🔐 `CHAVE_CRIPTO` não configurada: as senhas de app seriam salvas em texto puro. Gere uma chave com "
                   "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
                   "e coloque nos secrets.")
    st.caption("Use sempre **senha de app** do Google, nunca a senha normal. Contas novas: comece com limite baixo (30–50/dia).")
    with cartao():
        with st.form("form_nova_conta", clear_on_submit=True):
            a, b = st.columns(2)
            email = a.text_input("E-mail remetente").strip().lower()
            nome = a.text_input("Nome de exibição", value=str(cfg("EMPRESA_NOME"))).strip()
            senha = b.text_input("Senha de app", type="password").strip()
            limite = b.number_input("Limite diário de envios", min_value=10, max_value=campanha.LIMITE_MAXIMO_POR_CONTA, value=50)
            if st.form_submit_button("➕ Salvar conta", type="primary"):
                if not (email_valido(email) and senha):
                    st.warning("Preencha um e-mail válido e a senha de app.")
                else:
                    try:
                        repo.criar_conta(sb, cofre, email, senha, nome, limite)
                        st.success(f"✅ Conta {email} cadastrada!")
                        st.rerun()
                    except Exception as erro:
                        st.error(f"Erro ao cadastrar conta: {erro}")
    try:
        contas = repo.listar_contas(sb)
        usados = repo.contar_enviados_hoje(sb)
    except Exception as erro:
        st.error(f"Erro ao listar contas: {erro}")
        return
    if not contas:
        vazio("Nenhuma conta registrada ainda.")
        return
    legadas = [c for c in contas if c.get("senha_app") and not cofre.esta_protegida(c["senha_app"])]
    if legadas and cofre.ativo:
        st.warning(f"{len(legadas)} conta(s) ainda com senha em texto puro no banco.")
        if st.button("🔐 Proteger senhas existentes agora"):
            repo.proteger_senhas_existentes(sb, cofre, legadas)
            st.success("Senhas criptografadas.")
            st.rerun()
    for c in contas:
        c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
        c1.write(f"📧 **{c['email']}** ({c['nome_remetente']})")
        c2.write(f"Hoje: {usados.get(c['email'], 0)}/{c['limite_diario']}")
        c3.write("🟢 Ativa" if c["ativa"] else "🔴 Inativa")
        if c4.button("Desativar" if c["ativa"] else "Ativar", key=f"tog_{c['id']}"):
            repo.alternar_conta(sb, c["id"], not c["ativa"])
            st.rerun()


# ===================================================================== DESCADASTROS
def _pagina_descadastros(sb):
    st.caption("Quem responder **SAIR** deve entrar aqui. Esses e-mails são pulados em todos os disparos.")
    texto = st.text_area("Cole os e-mails (um por linha, ou separados por vírgula)", height=100, key="desc_txt")
    if st.button("➕ Adicionar à lista", type="primary"):
        validos = separar_emails(texto)
        if not validos:
            st.warning("Nenhum e-mail válido encontrado.")
        else:
            try:
                repo.adicionar_descadastros(sb, validos)
                _listas_de_bloqueio.clear()
                st.success(f"✅ {len(validos)} e-mail(s) adicionados.")
                st.rerun()
            except Exception as erro:
                st.error(f"Erro ao salvar (a tabela descadastros existe?): {erro}")
    try:
        lista = repo.listar_descadastros(sb)
    except Exception as erro:
        st.error(f"Erro ao listar: {erro}")
        return
    st.write(f"Total na lista: **{len(lista)}**")
    filtro = st.text_input("Buscar e-mail", key="desc_busca").strip().lower()
    visiveis = [r for r in lista if filtro in r["email"].lower()][:100]
    for r in visiveis:
        c1, c2 = st.columns([5, 1])
        c1.write(r["email"])
        if c2.button("Remover", key=f"rmdesc_{r['email']}"):
            repo.remover_descadastro(sb, r["email"])
            _listas_de_bloqueio.clear()
            st.rerun()


# ======================================================================== HISTÓRICO
def _pagina_historico(sb):
    try:
        dados = repo.historico(sb, 1000)
    except Exception as erro:
        st.error(f"Erro ao carregar histórico (a tabela envios_email existe?): {erro}")
        return
    if not dados:
        vazio("Nenhum envio registrado ainda.")
        return
    df = pd.DataFrame(dados)
    df["Horário"] = serie_utc_para_br(df["data_hora"])
    c1, c2 = st.columns(2)
    status = c1.selectbox("Status", ["Todos", "enviado", "erro"])
    busca = c2.text_input("Buscar protocolo ou e-mail").strip()
    if status != "Todos":
        df = df[df["status"] == status]
    if busca:
        df = df[df["protocolo"].astype(str).str.contains(busca, case=False, na=False, regex=False)
                | df["email"].astype(str).str.contains(busca, case=False, na=False, regex=False)]
    metricas([("Enviados (listados)", int((df["status"] == "enviado").sum())),
              ("Erros (listados)", int((df["status"] == "erro").sum()))])
    vitrine = df[["Horário", "nome", "email", "protocolo", "conta", "modelo", "status", "erro"]]
    st.dataframe(vitrine, hide_index=True, use_container_width=True)
    baixar_excel("📊 Baixar histórico (.xlsx)", gerar_excel({"Historico": vitrine}), "historico_envios.xlsx")
    st.caption("Mostrando os 1000 envios mais recentes.")


# ========================================================================== CLIQUES
@st.cache_data(ttl=60, show_spinner=False)
def _dados_cliques(_sb):
    cliques = pd.DataFrame(repo.listar_cliques(_sb))
    envios = pd.DataFrame(buscar_todos(_sb, "envios_email", "id,envio_id,data_hora", {"status": "enviado"}))
    return cliques, envios, contar(_sb, "envios_email", {"status": "enviado"})


def _pagina_cliques(sb):
    st.caption("Separa cliques de **pessoas** dos de **robôs** (scanners de segurança dos provedores de e-mail, "
               "que abrem todos os links logo após o envio).")
    if st.button("🔄 Atualizar"):
        _dados_cliques.clear()
    try:
        cliques, envios, total_enviados = _dados_cliques(sb)
    except Exception as erro:
        st.error(f"Erro ao carregar métricas de clique: {erro}")
        return
    if cliques.empty:
        vazio("Nenhum clique registrado até o momento.")
        return
    classificados = met.classificar_cliques(cliques, envios)
    r = met.resumir(classificados, total_enviados)
    metricas([("Cliques registrados", r.total), ("🤖 De robôs", r.robos), ("🙋 De pessoas", r.pessoas),
              ("Clientes que clicaram", r.envios_com_pessoa, "E-mails distintos com clique de pessoa"),
              ("Taxa real de clique", f"{r.taxa_pessoas}%", "Clientes que clicaram ÷ e-mails enviados")])
    with st.expander("🔍 Ver detalhes dos cliques"):
        st.dataframe(classificados, hide_index=True, use_container_width=True)


# ============================================================================ ENTRADA
def renderizar_disparador(sb):
    cabecalho("📧 Disparador de e-mails")
    secao = navegacao(SECOES, "nav_email")
    {"🚀 Disparos": _pagina_disparo, "✉️ Modelos": _pagina_modelos, "🔑 Contas": _pagina_contas,
     "🚫 Descadastros": _pagina_descadastros, "📜 Histórico": _pagina_historico,
     "📈 Cliques": _pagina_cliques}[secao](sb)
