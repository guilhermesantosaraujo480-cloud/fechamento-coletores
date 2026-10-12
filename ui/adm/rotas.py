"""Aba Rotas: sobe a planilha da operadora, confere, divide entre coletores e manda no WhatsApp."""
import io
import urllib.parse
import zipfile

import pandas as pd
import streamlit as st

from core import auditoria, auth, dados, sessao
from core.config import cfg
from core.exportacao import gerar_excel
from core.utils import data_br, hoje_br
from rotas import envio, leitura, mensagens, perfis as pf, processamento as pr, repositorio as repo, vinculos
from rotas.whatsapp import ErroWhats, criar_gateway
from ui.adm.usuarios import PADRAO_LOGIN
from ui.componentes import baixar_excel, cabecalho, cartao, metricas, navegacao, vazio

SECOES = ["🚚 Gerar e enviar", "👷 Coletores", "🏢 Empresas e grupos", "📜 Histórico"]
DICA_SQL = "Rode o `migracao_v3.sql` no Supabase (SQL Editor) para criar as tabelas da aba Rotas."


def _usuario():
    return sessao.usuario_atual()["usuario"]


def _gateway():
    return criar_gateway(cfg)


# =============================================================================== GERAR E ENVIAR
def _planilha_bruta():
    arquivo = st.file_uploader("📂 Planilha da operadora (.xls, .xlsx ou .csv)", type=["xls", "xlsx", "csv", "txt"],
                               key="rota_arquivo")
    if not arquivo:
        return None, None
    chave = f"{arquivo.name}:{arquivo.size}"
    guardado = st.session_state.get("rota_bruto")
    if not guardado or guardado[0] != chave:
        try:
            guardado = (chave, leitura.carregar_planilha(arquivo))
        except ValueError as erro:
            st.error(str(erro))
            return None, None
        st.session_state["rota_bruto"] = guardado
    return chave, guardado[1]


def _escolher_perfil(perfis, bruto, chave):
    nomes = [p.nome for p in perfis]
    detectado = pf.detectar_perfil(bruto.columns, perfis)
    escolha = st.selectbox("Empresa", nomes, index=nomes.index(detectado.nome) if detectado else 0,
                           key=f"rota_empresa_{chave}")
    if detectado:
        st.caption(f"🔎 Reconheci a planilha como **{detectado.nome}** pelas colunas. Mude acima se estiver errado.")
    else:
        st.warning("Não reconheci a empresa pelas colunas. Escolha acima ou cadastre em **Empresas e grupos**.")
    return perfis[nomes.index(escolha)]


def _conferencia(can, problemas):
    graves = int((problemas["Gravidade"] == "⚠️").sum()) if not problemas.empty else 0
    metricas([("📦 Coletas", len(can)), ("📍 Bairros", can["bairro"].replace("", pd.NA).nunique()),
              ("☎️ Com telefone", int(can["tel_ok"].sum())), ("⚠️ Pontos de atenção", graves)])
    if not problemas.empty:
        with st.expander(f"Ver {len(problemas)} ponto(s) de atenção"):
            st.dataframe(problemas, hide_index=True, use_container_width=True)


def _distribuir(can, coletores, chave, perfil):
    c1, c2, c3 = st.columns([3, 2, 1])
    escolhidos = c1.multiselect("Coletores desta rota", coletores, key=f"rota_sel_{chave}")
    modo = c2.radio("Distribuição", ["Dividir por bairro (equilibrado)", "Tudo para o primeiro da lista"],
                    key=f"rota_modo_{chave}")
    data_rota = c3.date_input("Data da rota", value=hoje_br(), format="DD/MM/YYYY", key=f"rota_data_{chave}")
    if not escolhidos:
        st.info("Escolha quem vai fazer esta rota.")
        return None, None, None
    atrib = (pr.dividir_entre(can, escolhidos) if modo.startswith("Dividir")
             else pd.Series(escolhidos[0], index=can.index, dtype=object))
    versao = hash((chave, perfil.nome, tuple(escolhidos), modo)) & 0xFFFFFF
    tela = can[["id", "nome", "endereco_completo", "bairro", "cidade", "telefone"]].copy()
    tela["Coletor"] = atrib
    st.caption("A divisão acima é automática. Para trocar uma coleta de coletor, use a coluna **Coletor** da tabela.")
    editado = st.data_editor(
        tela, key=f"rota_editor_{versao}", use_container_width=True,
        disabled=[c for c in tela.columns if c != "Coletor"],
        column_config={"id": "ID", "nome": "Cliente", "endereco_completo": "Endereço", "bairro": "Bairro",
                       "cidade": "Cidade", "telefone": "Telefone",
                       "Coletor": st.column_config.SelectboxColumn("Coletor", options=escolhidos + [pr.SEM_COLETOR], required=True)})
    return escolhidos, editado["Coletor"].reindex(can.index), data_rota


def _pacotes(sb, can, atrib, escolhidos, perfil, data_rota, incluir_mapa):
    cadastro = {c["nome_rota"]: c for c in repo.listar_coletores(sb)}
    pacotes = []
    for nome in escolhidos:
        sub = can[atrib == nome]
        if sub.empty:
            continue
        saida = pr.montar_saida(sub, perfil, incluir_mapa)
        pacotes.append({
            "coletor": nome, "qtd": len(sub), "sub": sub,
            "arquivo": f"Rota_{nome}_{data_rota:%d.%m.%Y}_{perfil.sufixo}.xlsx",
            "conteudo": gerar_excel({"Rota": saida}),
            "mensagem": mensagens.mensagem_rota(perfil.nome, nome, data_rota, sub),
            "telefone": pr.numero_whatsapp(cadastro.get(nome, {}).get("telefone", "")),
        })
    return pacotes


def _modo_manual(pacotes, perfil, data_rota):
    st.info("📋 **Modo manual** (nenhum gateway de WhatsApp configurado). Baixe a planilha de cada coletor e cole o texto "
            "no grupo. Para envio automático, veja `WHATS_PROVEDOR` no `secrets.exemplo.toml`.")
    for p in pacotes:
        with st.expander(f"👷 {p['coletor']} — {p['qtd']} coleta(s)"):
            st.download_button("📥 Baixar planilha", p["conteudo"], file_name=p["arquivo"], key=f"dl_{p['coletor']}",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            texto = mensagens.lista_para_copiar(perfil.nome, p["coletor"], data_rota, p["sub"])
            st.code(texto, language="text")
            st.link_button("🟢 Abrir WhatsApp com este texto", "https://api.whatsapp.com/send?text=" + urllib.parse.quote(texto))


def _enviar(sb, gateway, pacotes, perfil, data_rota):
    grupos = repo.listar_grupos(sb, perfil.nome)
    rotulos = {g["destino"]: f"{g['nome'] or g['destino']}" for g in grupos}
    destinos = st.multiselect("Enviar para o grupo", list(rotulos), format_func=rotulos.get,
                              default=list(rotulos)[:1], key="rota_destinos")
    individual = st.checkbox("Enviar também no WhatsApp individual de cada coletor (quando cadastrado)", key="rota_individual")
    if not grupos:
        st.warning(f"Nenhum grupo cadastrado para **{perfil.nome}**. Cadastre em **Empresas e grupos**.")
    ja = repo.enviados_na_data(sb, perfil.nome, data_rota)
    repetidos = [p["coletor"] for p in pacotes if p["coletor"] in ja]
    reenviar = True
    if repetidos:
        st.warning(f"⚠️ Já foi enviada rota de **{perfil.nome}** em {data_br(data_rota)} para: {', '.join(repetidos)}.")
        reenviar = st.checkbox("Quero enviar de novo mesmo assim", key="rota_reenviar")
    total = sum(len(destinos) + (1 if individual and p["telefone"] else 0) for p in pacotes)
    confirmou = st.checkbox(f"✅ Conferi a divisão e confirmo o envio ({total} mensagem(ns) no WhatsApp)", key="rota_confirma")
    if not st.button("📲 Enviar no WhatsApp", type="primary", use_container_width=True,
                     disabled=not (confirmou and reenviar and total)):
        return
    barra, feitos, usuario = st.progress(0.0), [0], _usuario()

    def registrar(res, pacote):
        feitos[0] += 1
        barra.progress(min(feitos[0] / max(total, 1), 1.0))
        repo.registrar_envio(sb, usuario, perfil.nome, data_rota, res, pacote["qtd"])

    resultados, parada = envio.enviar_rotas(gateway, pacotes, destinos, registrar, individual=individual)
    ok = sum(r.status == "enviado" for r in resultados)
    auditoria.registrar(sb, usuario, "rota_enviada", f"{perfil.nome} {data_br(data_rota)}: {ok}/{len(resultados)} mensagens")
    (st.success if ok == len(resultados) and not parada else st.warning)(f"{ok} de {len(resultados)} mensagem(ns) enviadas.")
    if parada:
        st.error(parada)
    st.dataframe(pd.DataFrame([r.__dict__ for r in resultados]), hide_index=True, use_container_width=True)


def _gerar(sb):
    try:
        perfis = repo.listar_perfis(sb)
        coletores = [c["nome_rota"] for c in repo.listar_coletores(sb, somente_ativos=True)]
    except Exception as erro:
        st.error(f"{DICA_SQL}\n\nDetalhe: {erro}")
        return
    if not coletores:
        vazio("Cadastre os coletores na seção **Coletores** primeiro.")
        return
    chave, bruto = _planilha_bruta()
    if bruto is None:
        return
    perfil = _escolher_perfil(perfis, bruto, chave)
    can, faltando = pr.aplicar_perfil(bruto, perfil)
    if faltando:
        st.error("Esta planilha não tem as colunas que o perfil espera: " + ", ".join(faltando)
                 + ". Escolha a empresa certa ou ajuste o perfil em **Empresas e grupos**.")
        return
    if can.empty:
        st.error("A planilha não tem nenhuma linha com dados.")
        return
    can = pr.ordenar_rota(can)
    _conferencia(can, pr.checar_qualidade(can))

    st.markdown("##### Distribuição")
    escolhidos, atrib, data_rota = _distribuir(can, coletores, chave, perfil)
    if escolhidos is None:
        return
    sem = int((atrib == pr.SEM_COLETOR).sum())
    if sem:
        st.warning(f"{sem} coleta(s) sem coletor: não serão enviadas.")
    incluir_mapa = st.checkbox("Incluir coluna **Mapa** (link do Google Maps de cada endereço)", value=True, key="rota_mapa")
    pacotes = _pacotes(sb, can, atrib, escolhidos, perfil, data_rota, incluir_mapa)
    if not pacotes:
        return
    st.dataframe(pd.DataFrame([{"Coletor": p["coletor"], "Coletas": p["qtd"],
                                "Bairros": p["sub"]["bairro"].replace("", pd.NA).nunique(),
                                "WhatsApp cadastrado": "sim" if p["telefone"] else "—"} for p in pacotes]),
                 hide_index=True, use_container_width=True)

    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        for p in pacotes:
            z.writestr(p["arquivo"], p["conteudo"])
    st.download_button("📦 Baixar todas as planilhas (.zip)", memoria.getvalue(), file_name=f"Rotas_{data_rota:%d.%m.%Y}_{perfil.sufixo}.zip",
                       mime="application/zip", use_container_width=True)

    st.markdown("##### Envio")
    gateway = _gateway()
    if gateway is None:
        _modo_manual(pacotes, perfil, data_rota)
    else:
        with cartao():
            st.caption(f"🟢 WhatsApp via {gateway.nome}")
            _enviar(sb, gateway, pacotes, perfil, data_rota)


# ===================================================================================== COLETORES
def _novo_coletor(sb, usuarios):
    ctr = st.session_state.setdefault("rota_novo_ctr", 0)
    livres = {u["id"]: f"{u['nome_completo']} ({u['usuario']})" for u in usuarios if u.get("cargo") == "COLETOR"}
    with cartao():
        st.markdown("**➕ Novo coletor**")
        nome = st.text_input("Nome na rota (ex.: GEOVAN)", key=f"rc_nome_{ctr}")
        telefone = st.text_input("WhatsApp (opcional, com DDD)", key=f"rc_tel_{ctr}")
        login = st.radio("Login no sistema", ["Sem login", "Vincular a login existente", "Criar login novo"],
                         key=f"rc_login_{ctr}")
        usuario_id, novo = None, {}
        if login == "Vincular a login existente":
            usuario_id = st.selectbox("Login", list(livres), format_func=livres.get, index=None,
                                      placeholder="Escolha...", key=f"rc_vinc_{ctr}")
        elif login == "Criar login novo":
            novo["nome"] = st.text_input("Nome completo no sistema", value=nome.title(), key=f"rc_nc_{ctr}")
            novo["login"] = st.text_input("Login", key=f"rc_lg_{ctr}").strip().lower()
            novo["senha"] = st.text_input(f"Senha (mínimo {auth.MIN_SENHA})", type="password", key=f"rc_sn_{ctr}")
        if not st.button("Cadastrar coletor", type="primary", use_container_width=True, key=f"rc_ok_{ctr}"):
            return
        if not nome.strip():
            st.error("Informe o nome na rota.")
            return
        try:
            if login == "Criar login novo":
                problema = (None if PADRAO_LOGIN.fullmatch(novo["login"]) else "Login inválido (3 a 30 letras minúsculas, números, . - _).") \
                    or auth.validar_senha_nova(novo["senha"]) or (None if novo["nome"].strip() else "Informe o nome completo.")
                if problema:
                    st.error(problema)
                    return
                if sb.table("usuarios").select("id").eq("usuario", novo["login"]).limit(1).execute().data:
                    st.error("Esse login já existe.")
                    return
                criado = sb.table("usuarios").insert({"usuario": novo["login"], "senha": auth.gerar_hash_senha(novo["senha"]),
                                                      "nome_completo": novo["nome"].strip(), "cargo": "COLETOR"}).execute().data
                usuario_id = criado[0]["id"] if criado else None
                auditoria.registrar(sb, _usuario(), "usuario_criado", f"{novo['login']} (via rotas)")
            repo.criar_coletor(sb, nome, pr.numero_whatsapp(telefone), usuario_id)
        except ValueError as erro:
            st.error(str(erro))
            return
        except Exception as erro:
            st.error(f"Erro ao cadastrar: {erro}")
            return
        dados.invalidar()
        st.session_state["rota_novo_ctr"] = ctr + 1
        st.toast(f"{nome.strip().upper()} cadastrado.", icon="✅")
        st.rerun()


def _editar_coletor(sb, lista, usuarios):
    por_id = {u["id"]: u for u in usuarios}
    rotulo_login = lambda uid: f"{por_id[uid]['nome_completo']} ({por_id[uid]['usuario']})" if uid in por_id else "—"  # noqa: E731
    with cartao():
        st.markdown("**👷 Coletores de rota**")
        if not lista:
            vazio("Nenhum coletor cadastrado.")
            return
        st.dataframe([{"Nome na rota": c["nome_rota"], "Login": rotulo_login(c.get("usuario_id")),
                       "WhatsApp": c.get("telefone") or "—", "Situação": "🟢 Ativo" if c["ativo"] else "🔴 Inativo"}
                      for c in lista], hide_index=True, use_container_width=True)
        rotulos = {c["id"]: c["nome_rota"] for c in lista}
        escolhido = st.selectbox("Editar coletor", list(rotulos), format_func=rotulos.get, index=None,
                                 placeholder="Escolha...", key="rc_editar")
        if escolhido is not None:
            c = next(x for x in lista if x["id"] == escolhido)
            telefone = st.text_input("WhatsApp", value=c.get("telefone") or "", key=f"rce_tel_{escolhido}")
            logins = [None] + [u["id"] for u in usuarios if u.get("cargo") == "COLETOR"]
            atual = c.get("usuario_id") if c.get("usuario_id") in logins else None
            login = st.selectbox("Login vinculado", logins, index=logins.index(atual), key=f"rce_lg_{escolhido}",
                                 format_func=lambda uid: "(nenhum)" if uid is None else rotulo_login(uid))
            ativo = st.checkbox("Ativo (aparece na hora de gerar rotas)", value=c["ativo"], key=f"rce_at_{escolhido}")
            if st.button("💾 Salvar alterações", key=f"rce_ok_{escolhido}"):
                repo.atualizar_coletor(sb, escolhido, telefone=pr.numero_whatsapp(telefone), usuario_id=login, ativo=ativo)
                st.toast("Coletor atualizado.", icon="✅")
                st.rerun()
        sugestoes = vinculos.sugerir_vinculos(lista, usuarios)
        if sugestoes:
            with st.expander(f"🪄 {len(sugestoes)} vínculo(s) sugerido(s) com logins que já existem"):
                nomes = {c["id"]: c["nome_rota"] for c in lista}
                st.dataframe([{"Coletor de rota": nomes[cid], "Login sugerido": rotulo_login(uid), "Semelhança": f"{int(n * 100)}%"}
                              for cid, uid, n in sugestoes], hide_index=True, use_container_width=True)
                if st.button("Aplicar todas as sugestões", key="rc_aplicar_sug"):
                    for cid, uid, _ in sugestoes:
                        repo.atualizar_coletor(sb, cid, usuario_id=uid)
                    st.toast("Vínculos aplicados.", icon="🔗")
                    st.rerun()


def _coletores(sb):
    try:
        lista = repo.listar_coletores(sb)
        usuarios, _ = dados.listar_usuarios(sb)
    except Exception as erro:
        st.error(f"{DICA_SQL}\n\nDetalhe: {erro}")
        return
    esquerda, direita = st.columns([2, 3])
    with esquerda:
        _novo_coletor(sb, usuarios)
    with direita:
        _editar_coletor(sb, lista, usuarios)


# ============================================================================ EMPRESAS E GRUPOS
def _grupos(sb, perfis):
    gateway = _gateway()
    with cartao():
        st.markdown("**💬 Grupos de WhatsApp**")
        st.caption("O `destino` é o ID do grupo (termina em `@g.us`). Com o gateway conectado, use **Buscar meus grupos**.")
        empresas = [p.nome for p in perfis]
        if gateway and st.button("🔎 Buscar meus grupos no WhatsApp", key="rg_buscar"):
            try:
                st.session_state["rota_grupos_encontrados"] = gateway.listar_grupos()
            except ErroWhats as erro:
                st.error(str(erro))
        achados = st.session_state.get("rota_grupos_encontrados", [])
        destino_pre = nome_pre = ""
        if achados:
            opcoes = {g["destino"]: g["nome"] for g in achados}
            escolhido = st.selectbox("Grupos encontrados", list(opcoes), format_func=opcoes.get, index=None,
                                     placeholder="Escolha um grupo...", key="rg_achado")
            destino_pre, nome_pre = (escolhido or ""), (opcoes.get(escolhido, "") if escolhido else "")
        c1, c2, c3 = st.columns([2, 2, 3])
        empresa = c1.selectbox("Empresa", empresas, key="rg_empresa")
        nome = c2.text_input("Nome do grupo", value=nome_pre, key=f"rg_nome_{nome_pre}")
        destino = c3.text_input("Destino (ID do grupo ou número com DDI)", value=destino_pre, key=f"rg_dest_{destino_pre}")
        b1, b2 = st.columns(2)
        if b1.button("➕ Salvar grupo", type="primary", use_container_width=True, key="rg_salvar"):
            if destino.strip():
                repo.criar_grupo(sb, empresa, nome, destino)
                st.toast("Grupo salvo.", icon="✅")
                st.rerun()
            else:
                st.error("Informe o destino.")
        if gateway and b2.button("📨 Enviar mensagem de teste", use_container_width=True, key="rg_teste"):
            try:
                gateway.enviar_texto(destino.strip(), "✅ Teste do sistema de rotas: se você leu isto, a conexão está funcionando.")
                st.success("Mensagem de teste enviada.")
            except ErroWhats as erro:
                st.error(str(erro))
        for g in repo.listar_grupos(sb):
            a, b = st.columns([5, 1])
            a.write(f"**{g['empresa']}** → {g['nome'] or '—'} · `{g['destino']}`")
            if b.button("Remover", key=f"rg_rm_{g['id']}"):
                repo.remover_grupo(sb, g["id"])
                st.rerun()


def _nova_empresa(sb):
    with cartao():
        st.markdown("**🏢 Cadastrar nova empresa (novo formato de planilha)**")
        nome = st.text_input("Nome da empresa", key="rp_nome")
        sufixo = st.text_input("Final do nome do arquivo", placeholder="EMPRESA XYZ", key="rp_sufixo")
        amostra = st.file_uploader("Planilha de exemplo dessa empresa", type=["xls", "xlsx", "csv", "txt"], key="rp_amostra")
        if not amostra:
            st.caption("Envie uma planilha de exemplo para escolher quais colunas são cada campo.")
            return
        try:
            colunas = list(leitura.carregar_planilha(amostra).columns)
        except ValueError as erro:
            st.error(str(erro))
            return
        opcoes = ["(não tem)"] + colunas
        mapa, cols = {}, st.columns(3)
        padrao = {c.lower(): c for c in colunas}
        for i, (campo, rotulo) in enumerate(pf.CAMPOS.items()):
            sugestao = next((padrao[k] for k in padrao if k == rotulo.split(" / ")[0].lower() or k == campo), "(não tem)")
            escolha = cols[i % 3].selectbox(rotulo, opcoes, index=opcoes.index(sugestao), key=f"rp_{campo}")
            mapa[campo] = None if escolha == "(não tem)" else escolha
        if st.button("💾 Salvar empresa", type="primary", key="rp_salvar"):
            if not nome.strip():
                st.error("Informe o nome da empresa.")
            elif not (mapa["endereco"] and mapa["nome"]):
                st.error("Escolha pelo menos as colunas de nome do cliente e endereço.")
            else:
                try:
                    repo.salvar_perfil(sb, pf.perfil_a_partir_do_mapa(nome, sufixo, mapa))
                    st.toast("Empresa cadastrada.", icon="✅")
                    st.rerun()
                except Exception as erro:
                    st.error(f"Erro ao salvar: {erro}")


def _empresas(sb):
    try:
        perfis = repo.listar_perfis(sb)
        repo.listar_grupos(sb)
    except Exception as erro:
        st.error(f"{DICA_SQL}\n\nDetalhe: {erro}")
        return
    st.dataframe([{"Empresa": p.nome, "Arquivo termina em": p.sufixo, "Origem": "padrão" if p.padrao else "cadastrada",
                   "Colunas lidas": len(p.mapa)} for p in perfis], hide_index=True, use_container_width=True)
    _grupos(sb, perfis)
    _nova_empresa(sb)


# ========================================================================================= HISTÓRICO
def _historico(sb):
    try:
        linhas = repo.historico(sb)
    except Exception as erro:
        st.error(f"{DICA_SQL}\n\nDetalhe: {erro}")
        return
    if not linhas:
        vazio("Nenhuma rota enviada ainda.")
        return
    df = pd.DataFrame(linhas)
    df["data_rota"] = df["data_rota"].map(data_br)
    st.dataframe(df[["data_rota", "empresa", "coletor", "qtd", "destino", "status", "detalhe", "usuario"]].rename(columns={
        "data_rota": "Data da rota", "empresa": "Empresa", "coletor": "Coletor", "qtd": "Coletas", "destino": "Destino",
        "status": "Status", "detalhe": "Detalhe", "usuario": "Enviado por"}), hide_index=True, use_container_width=True)


# ========================================================================================== ENTRADA
def render(sb):
    cabecalho("🚚 Rotas", "Suba a planilha da operadora; o sistema confere, divide entre os coletores e manda no WhatsApp.")
    secao = navegacao(SECOES, "nav_rotas")
    {"🚚 Gerar e enviar": _gerar, "👷 Coletores": _coletores, "🏢 Empresas e grupos": _empresas,
     "📜 Histórico": _historico}[secao](sb)
