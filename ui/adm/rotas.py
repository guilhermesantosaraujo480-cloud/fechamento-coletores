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
from rotas import (acompanhamento, avisos, distribuicao, envio, leitura, mensagens, nomes, perfis as pf,
                   processamento as pr, repositorio as repo, vinculos)
from rotas.whatsapp import ErroWhats, criar_gateway
from ui.adm.usuarios import PADRAO_LOGIN
from ui.componentes import baixar_excel, cabecalho, cartao, metricas, navegacao, vazio

SECOES = ["🚚 Gerar e enviar", "📊 Acompanhamento", "👷 Coletores", "🏢 Empresas e grupos", "📜 Histórico"]
DICA_SQL = "Rode o `migracao_v3.sql` e o `migracao_v4.sql` no Supabase (SQL Editor) para criar as tabelas da aba Rotas."
MODO_PLATAFORMA = "📋 Usar o coletor que já está na planilha"
MODO_BAIRRO = "Dividir por bairro (equilibrado)"
MODO_PRIMEIRO = "Tudo para o primeiro da lista"
ICONE_TIPO = {"normal": "", "retentativa": "🔁 retentativas", "deposito": "📦 depósito"}


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
    lista_nomes = [p.nome for p in perfis]
    detectado = pf.detectar_perfil(bruto.columns, perfis)
    escolha = st.selectbox("Empresa", lista_nomes, index=lista_nomes.index(detectado.nome) if detectado else 0,
                           key=f"rota_empresa_{chave}")
    if detectado:
        st.caption(f"🔎 Reconheci a planilha como **{detectado.nome}** pelas colunas. Mude acima se estiver errado.")
    else:
        st.warning("Não reconheci a empresa pelas colunas. Escolha acima ou cadastre em **Empresas e grupos**.")
    return perfis[lista_nomes.index(escolha)]


def _conferencia(can, problemas):
    graves = int((problemas["Gravidade"] == "⚠️").sum()) if not problemas.empty else 0
    metricas([("📦 Coletas", len(can)), ("📍 Bairros", can["bairro_ef"].nunique()),
              ("☎️ Com telefone", int(can["tel_ok"].sum())), ("⚠️ Pontos de atenção", graves)])
    c = avisos.contagem(can)
    if any(c[k] for k in ("prioridade", "hoje", "vencidas", "risco")):
        st.warning(avisos.linha_resumo(c) + "  — veja a coluna **Avisos** na tabela abaixo.")
    if not problemas.empty:
        with st.expander(f"Ver {len(problemas)} ponto(s) de atenção"):
            st.dataframe(problemas, hide_index=True, use_container_width=True)


def _escolher_mensagem(sb):
    """Lista de mensagens prontas (do sistema + as suas, salvas no banco) e campo para editar/salvar. Devolve o texto escolhido."""
    salvas = repo.listar_mensagens(sb)
    opcoes = {n: t for n, t in pr.MODELOS_WHATS}
    opcoes.update({f"⭐ {m['nome']}": m["texto"] for m in salvas})
    nome = st.selectbox("Mensagem pronta", list(opcoes), key="rota_msg_escolha")
    texto = st.text_area("Texto (pode editar)", value=opcoes[nome], height=90, key=f"rota_msg_texto_{abs(hash(nome)) % 100000}")
    st.caption("Campos: " + " · ".join(f"`{c}`" for c in pr.CAMPOS_MENSAGEM) + ". Mensagem curta = link curto.")
    st.caption("Exemplo: " + pr.link_whatsapp("11987654321", "", "MARIA DA SILVA", "GEOVAN", texto, EXEMPLO_ENDERECO))
    c1, c2 = st.columns([3, 1])
    novo_nome = c1.text_input("Salvar como (nome)", key="rota_msg_novo_nome", placeholder="Ex.: Aviso de chegada")
    if c2.button("💾 Salvar", key="rota_msg_salvar") and novo_nome.strip() and texto.strip():
        try:
            repo.salvar_mensagem(sb, novo_nome, texto)
            st.toast("Mensagem salva.", icon="✅")
            st.rerun()
        except Exception as erro:
            st.error(f"Não consegui salvar (rodou o `migracao_v7.sql`?): {erro}")
    mapa_id = {f"⭐ {m['nome']}": m["id"] for m in salvas}
    if nome in mapa_id and st.button("🗑️ Apagar esta mensagem salva", key="rota_msg_apagar"):
        repo.remover_mensagem(sb, mapa_id[nome])
        st.rerun()
    return texto


EXEMPLO_ENDERECO = {"rua": "RUA DAS FLORES", "numero": "120", "bairro": "CENTRO", "cidade": "SUZANO", "protocolo": "4044738"}


def _opcoes(sb):
    with cartao():
        c1, c2, c3, c4, c5 = st.columns([1.3, 1.8, 1.8, 1.5, 2])
        data_rota = c1.date_input("Data da rota", value=hoje_br(), format="DD/MM/YYYY", key="rota_data")
        urgentes = c2.checkbox("🔴 Urgentes no topo", value=False, key="rota_urgentes",
                               help="Prioridade máxima, agenda de hoje e agenda vencida vêm primeiro em cada planilha.")
        avisos_col = c3.checkbox("➕ Coluna **Avisos**", value=True, key="rota_avisos")
        mapa = c4.checkbox("🗺️ Coluna **Mapa**", value=True, key="rota_mapa")
        whats = c5.checkbox("💬 Coluna **WhatsApp** (link do cliente)", value=True, key="rota_whats",
                            help="Link que abre a conversa com o cliente já com a mensagem escrita. Só para celulares; "
                                 "telefone fixo fica em branco.")
        modelo = pr.MENSAGEM_WHATS_PADRAO
        if whats:
            with st.expander("✏️ Mensagem que vai no link do WhatsApp"):
                modelo = _escolher_mensagem(sb)
    return data_rota, urgentes, avisos_col, mapa, whats, modelo


def _casar_nomes(sb, can, coletores, chave):
    """Liga o nome do coletor que veio na planilha ao coletor da rota. Devolve a série de coletores (SEM_COLETOR se vazio)."""
    apelidos = repo.listar_apelidos(sb)
    tabela = nomes.mapear(can["coletor"], coletores, apelidos)
    ajustes = {}
    desconhecidos = [t for t in tabela if t["rota"] is None]
    with st.expander(f"🔤 Nomes do coletor na planilha ({len(tabela)})" + (f" — ⚠️ {len(desconhecidos)} não reconhecido(s)" if desconhecidos else " ✅"),
                     expanded=bool(desconhecidos)):
        st.dataframe([{"Nome na planilha": t["bruto"], "Coletor da rota": t["rota"] or "— não reconhecido —",
                       "Como casei": t["origem"], "OS": t["qtd"]} for t in tabela], hide_index=True, use_container_width=True)
        if desconhecidos:
            st.caption("Escolha quem é cada um. Marque “lembrar” para o sistema não perguntar de novo.")
            lembrar = st.checkbox("💾 Lembrar essas ligações para os próximos relatórios", value=True, key=f"rota_lembrar_{chave}")
            for k, t in enumerate(desconhecidos):
                escolha = st.selectbox(f"{t['bruto']}  ({t['qtd']} OS)", coletores, index=None, placeholder="Escolha o coletor...",
                                       key=f"rota_aj_{chave}_{k}")
                if escolha:
                    ajustes[t["bruto"]] = escolha
            if ajustes and lembrar and st.button("Salvar ligações", key=f"rota_aj_ok_{chave}"):
                try:
                    for bruto, rota in ajustes.items():
                        repo.salvar_apelido(sb, nomes.normalizar_nome(bruto), rota)
                    st.toast("Ligações salvas.", icon="🔗")
                except Exception as erro:
                    st.error(f"Não consegui salvar (rodou o `migracao_v4.sql`?): {erro}")
    return pd.Series(nomes.atribuir(can["coletor"], coletores, apelidos, ajustes), index=can.index, dtype=object)


def _sugerir(can, atrib, tipos, escolhidos, chave):
    """Botão que sugere coletor para as OS sem dono (regras explicáveis). Devolve (atrib com sugestões, razões)."""
    sem = int((atrib == pr.SEM_COLETOR).sum())
    razoes = pd.Series("", index=can.index, dtype=object)
    if not sem:
        return atrib, razoes
    chave_sug = f"rota_sug_{chave}"
    with cartao():
        st.markdown(f"**🧠 {sem} OS sem coletor.** O sistema pode sugerir quem leva cada uma.")
        st.caption("Regras: “mudou-se” → depósito · já foi à rua → retentativas · OS nova → quem já atende o bairro/CEP, "
                   "depois quem atende a cidade com menos carga. Nada é enviado antes de você conferir.")
        normais = [c for c in escolhidos if tipos.get(c, "normal") == "normal"]
        quem = st.multiselect("Quem pode receber OS novas", normais, default=normais, key=f"rota_quem_{chave}")
        b1, b2 = st.columns(2)
        if b1.button("🧠 Sugerir coletor para as OS sem dono", type="primary", use_container_width=True, key=f"rota_sug_btn_{chave}"):
            st.session_state[chave_sug] = distribuicao.sugerir(can, atrib, tipos, quem)
        if st.session_state.get(chave_sug) is not None and b2.button("Desfazer sugestões", use_container_width=True, key=f"rota_sug_off_{chave}"):
            st.session_state.pop(chave_sug, None)
    sug = st.session_state.get(chave_sug)
    if sug is not None and not sug.empty:
        atrib = atrib.copy()
        atrib.loc[sug.index] = sug["sugestao"]
        razoes.loc[sug.index] = sug["razao"]
        resumo = sug["sugestao"].value_counts()
        st.success("Sugestão aplicada: " + " · ".join(f"{c} +{n}" for c, n in resumo.items()) + ". Ajuste na tabela se quiser.")
    return atrib, razoes


def _distribuir(sb, can, coletores, tipos, chave, perfil):
    tem_plataforma = bool((can["coletor"] != "").any())
    modos = ([MODO_PLATAFORMA] if tem_plataforma else []) + [MODO_BAIRRO, MODO_PRIMEIRO]
    modo = st.radio("Distribuição", modos, horizontal=True, key=f"rota_modo_{chave}",
                    help="Se você já distribuiu na plataforma da empresa, use o coletor que veio na planilha.")
    razoes = pd.Series("", index=can.index, dtype=object)
    if modo == MODO_PLATAFORMA:
        atrib = _casar_nomes(sb, can, coletores, chave)
        achados = [c for c in sorted(set(atrib) - {pr.SEM_COLETOR})]
        escolhidos = st.multiselect("Coletores desta rota", coletores, default=achados, key=f"rota_sel_{chave}_plat",
                                    help="Já vêm marcados os coletores que aparecem na planilha. Tire alguém para deixar as OS dele de fora.")
        atrib = atrib.where(atrib.isin(escolhidos), pr.SEM_COLETOR)
        atrib, razoes = _sugerir(can, atrib, tipos, escolhidos, chave)
        escolhidos = sorted(set(escolhidos) | (set(atrib) - {pr.SEM_COLETOR}))
    else:
        escolhidos = st.multiselect("Coletores desta rota", coletores, key=f"rota_sel_{chave}")
        if not escolhidos:
            st.info("Escolha quem vai fazer esta rota.")
            return None, None
        atrib = (pr.dividir_entre(can, escolhidos) if modo == MODO_BAIRRO
                 else pd.Series(escolhidos[0], index=can.index, dtype=object))
    if not escolhidos:
        st.info("Nenhum coletor reconhecido. Escolha quem vai fazer esta rota.")
        return None, None
    versao = hash((chave, perfil.nome, tuple(escolhidos), modo, tuple(atrib.tolist()))) & 0xFFFFFF
    tela = can[["id", "nome", "endereco_completo", "bairro", "avisos"]].copy()
    if razoes.any():
        tela["Por que"] = razoes
    tela["Coletor"] = atrib
    st.caption("Para trocar uma coleta de coletor, use a coluna **Coletor** da tabela (clique e escolha).")
    editado = st.data_editor(
        tela, key=f"rota_editor_{versao}", use_container_width=True, height=360,
        disabled=[c for c in tela.columns if c != "Coletor"],
        column_config={"id": "ID", "nome": "Cliente", "endereco_completo": "Endereço", "bairro": "Bairro", "avisos": "Avisos",
                       "Coletor": st.column_config.SelectboxColumn("Coletor", options=escolhidos + [pr.SEM_COLETOR], required=True)})
    return escolhidos, editado["Coletor"].reindex(can.index)


def _pacotes(sb, can, atrib, escolhidos, perfil, data_rota, incluir_mapa, incluir_avisos, incluir_whats=False, modelo_whats=None):
    lista = repo.listar_coletores(sb)
    cadastro = {c["nome_rota"]: c for c in lista}
    tipos = repo.tipos_dos_coletores(lista)
    pacotes = []
    for nome in escolhidos:
        sub = can[atrib == nome]
        if sub.empty:
            continue
        saida = pr.montar_saida(sub, perfil, incluir_mapa, incluir_avisos, incluir_whats, modelo_whats, coletor=nome)
        pacotes.append({
            "coletor": nome, "qtd": len(sub), "sub": sub, "tipo": tipos.get(nome, "normal"),
            "urgentes": int(sub["urgente"].sum()),
            "arquivo": f"Rota_{nome}_{data_rota:%d.%m.%Y}_{perfil.sufixo}.xlsx",
            "conteudo": gerar_excel({"Rota": saida}),
            "mensagem": mensagens.mensagem_rota(perfil.nome, nome, data_rota, sub),
            "telefone": pr.numero_whatsapp(cadastro.get(nome, {}).get("telefone", "")),
        })
    return pacotes


def _escolher_quem_recebe(pacotes):
    """Tabela com 'Enviar?' marcado para todos, menos os coletores de depósito."""
    base = pd.DataFrame([{"Enviar?": p["tipo"] != "deposito", "Coletor": p["coletor"], "Coletas": p["qtd"],
                          "Urgentes": p["urgentes"], "Bairros": p["sub"]["bairro_ef"].nunique(),
                          "Tipo": ICONE_TIPO.get(p["tipo"], "") or "normal",
                          "WhatsApp": "sim" if p["telefone"] else "—"} for p in pacotes])
    versao = hash(tuple((p["coletor"], p["qtd"]) for p in pacotes)) & 0xFFFFFF
    editado = st.data_editor(base, hide_index=True, use_container_width=True, key=f"rota_quem_envia_{versao}",
                             disabled=[c for c in base.columns if c != "Enviar?"],
                             column_config={"Enviar?": st.column_config.CheckboxColumn("Enviar?")})
    marcados = set(editado.loc[editado["Enviar?"], "Coletor"])
    if any(p["tipo"] == "deposito" for p in pacotes):
        st.caption("📦 Coletores de **depósito** (OS paradas) vêm desmarcados: o arquivo é gerado, mas não vai para o WhatsApp.")
    return [p for p in pacotes if p["coletor"] in marcados]


def _guardar_fotografia(sb, can, atrib, perfil, data_rota):
    linhas = acompanhamento.montar_snapshot(can, atrib, perfil.nome, data_rota)
    n = repo.salvar_snapshot(sb, linhas)
    repo.limpar_snapshots_antigos(sb)
    return n


def _modo_manual(pacotes, perfil, data_rota):
    st.info("📋 **Modo manual** (nenhum gateway de WhatsApp configurado). Baixe a planilha de cada coletor e cole o texto "
            "no grupo. Para envio automático, veja `WHATS_PROVEDOR` no `secrets.exemplo.toml`.")
    for p in pacotes:
        with st.expander(f"👷 {p['coletor']} — {p['qtd']} coleta(s)"):
            st.download_button("📥 Baixar planilha", p["conteudo"], file_name=p["arquivo"], key=f"dl_{p['coletor']}",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.caption("Mensagem curta (legenda do arquivo):")
            st.code(p["mensagem"], language="text")
            texto = mensagens.lista_para_copiar(perfil.nome, p["coletor"], data_rota, p["sub"])
            st.caption("Lista completa em texto:")
            st.code(texto, language="text")
            st.link_button("🟢 Abrir WhatsApp com este texto", "https://api.whatsapp.com/send?text=" + urllib.parse.quote(texto))


def _enviar(sb, gateway, pacotes, perfil, data_rota, depois=None):
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
    if ok and depois:
        try:
            depois()
            st.caption("📸 Fotografia do dia guardada para o acompanhamento.")
        except Exception as erro:
            st.caption(f"Não consegui guardar a fotografia do dia (rodou o `migracao_v4.sql`?): {erro}")
    (st.success if ok == len(resultados) and not parada else st.warning)(f"{ok} de {len(resultados)} mensagem(ns) enviadas.")
    if parada:
        st.error(parada)
    st.dataframe(pd.DataFrame([r.__dict__ for r in resultados]), hide_index=True, use_container_width=True)


def _gerar(sb):
    try:
        perfis = repo.listar_perfis(sb)
        lista = repo.listar_coletores(sb)
    except Exception as erro:
        st.error(f"{DICA_SQL}\n\nDetalhe: {erro}")
        return
    ativos = [c["nome_rota"] for c in lista if c["ativo"]]
    tipos = repo.tipos_dos_coletores(lista)
    if not ativos:
        vazio("Cadastre os coletores na seção **Coletores** primeiro.")
        return
    st.caption("Fluxo: distribua na plataforma da empresa → baixe o relatório geral → suba aqui. "
               "O sistema separa por coletor, confere e manda no WhatsApp.")
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
    data_rota, urgentes, incluir_avisos, incluir_mapa, incluir_whats, modelo_whats = _opcoes(sb)
    can = pr.ordenar_rota(avisos.aplicar_avisos(can, data_rota), urgentes_primeiro=urgentes)
    _conferencia(can, pr.checar_qualidade(can))

    st.markdown("##### Distribuição")
    escolhidos, atrib = _distribuir(sb, can, ativos, tipos, chave, perfil)
    if escolhidos is None:
        return
    sem = int((atrib == pr.SEM_COLETOR).sum())
    if sem:
        st.warning(f"{sem} coleta(s) sem coletor: não serão enviadas.")
    pacotes = _pacotes(sb, can, atrib, escolhidos, perfil, data_rota, incluir_mapa, incluir_avisos, incluir_whats, modelo_whats)
    if not pacotes:
        return
    st.markdown("##### Quem recebe")
    para_enviar = _escolher_quem_recebe(pacotes)

    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        for p in pacotes:
            z.writestr(p["arquivo"], p["conteudo"])
    b1, b2, b3 = st.columns(3)
    b1.download_button("📦 Baixar todas as planilhas (.zip)", memoria.getvalue(), file_name=f"Rotas_{data_rota:%d.%m.%Y}_{perfil.sufixo}.zip",
                       mime="application/zip", use_container_width=True)
    plataforma = distribuicao.arquivo_para_plataforma(can, atrib, perfil)
    b2.download_button("🔁 Divisão para a plataforma (.xlsx)", gerar_excel({"Divisao": plataforma}),
                       file_name=f"Divisao_{perfil.sufixo}_{data_rota:%d.%m.%Y}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True,
                       help="ID da OS + coletor. Serve para conferir ou subir em massa na plataforma (o formato exato de importação "
                            "de cada plataforma pode precisar de ajuste).")
    if b3.button("💾 Guardar para acompanhamento", use_container_width=True, key="rota_guardar"):
        try:
            n = _guardar_fotografia(sb, can, atrib, perfil, data_rota)
            st.toast(f"Fotografia guardada ({n} OS).", icon="📸")
        except Exception as erro:
            st.error(f"{DICA_SQL}\n\nDetalhe: {erro}")

    st.markdown("##### Envio")
    if not para_enviar:
        st.info("Marque pelo menos um coletor em **Enviar?** para liberar o envio.")
        return
    gateway = _gateway()
    if gateway is None:
        _modo_manual(para_enviar, perfil, data_rota)
    else:
        with cartao():
            st.caption(f"🟢 WhatsApp via {gateway.nome}")
            _enviar(sb, gateway, para_enviar, perfil, data_rota,
                    depois=lambda: _guardar_fotografia(sb, can, atrib, perfil, data_rota))


# ================================================================================ ACOMPANHAMENTO
def _acompanhamento(sb):
    try:
        perfis = repo.listar_perfis(sb)
    except Exception as erro:
        st.error(f"{DICA_SQL}\n\nDetalhe: {erro}")
        return
    st.caption("Compara os relatórios dia a dia: quem tinha quantas OS, quantas saíram da lista (coletadas, canceladas ou "
               "encerradas na plataforma) e quanto trabalho novo entrou. Guarde a fotografia em **Gerar e enviar**.")
    empresa = st.selectbox("Empresa", [p.nome for p in perfis], key="acomp_empresa")
    try:
        datas = repo.datas_de_snapshot(sb, empresa, 8)
    except Exception as erro:
        st.error(f"{DICA_SQL}\n\nDetalhe: {erro}")
        return
    if not datas:
        vazio("Ainda não há fotografias dessa empresa. Em **Gerar e enviar**, clique em “Guardar para acompanhamento”.")
        return
    c1, c2 = st.columns(2)
    atual = c1.selectbox("Dia", datas, format_func=data_br, key="acomp_atual")
    anteriores = [d for d in datas if d < atual]
    anterior = c2.selectbox("Comparar com", anteriores, format_func=data_br, key="acomp_ant",
                            index=0 if anteriores else None, placeholder="(sem dia anterior)")
    hoje_snap = repo.ler_snapshot(sb, empresa, atual)
    carga = pd.DataFrame(hoje_snap)
    if carga.empty:
        vazio("Fotografia vazia.")
        return
    if not anterior:
        resumo = carga.groupby("coletor").agg(OS=("os_id", "count"), Urgentes=("urgente", "sum")).reset_index().rename(columns={"coletor": "Coletor"})
        metricas([("📦 OS na lista", len(carga)), ("👷 Coletores", carga["coletor"].nunique())])
        st.dataframe(resumo.sort_values("OS", ascending=False), hide_index=True, use_container_width=True)
        st.info("Guarde a fotografia de outro dia para ver a comparação.")
        return
    comp = acompanhamento.comparar(repo.ler_snapshot(sb, empresa, anterior), hoje_snap)
    saiu, entrou = len(comp["saiu"]), len(comp["entrou"])
    metricas([("📦 Antes", comp["total_antes"]), ("📦 Hoje", comp["total_hoje"]), ("✅ Saíram da lista", saiu),
              ("🆕 Entraram", entrou), ("📉 % que saiu", f"{round(100 * saiu / max(comp['total_antes'], 1), 1)}%")])
    st.dataframe(comp["por_coletor"].sort_values("Hoje", ascending=False), hide_index=True, use_container_width=True)
    baixar_excel("📊 Baixar comparação (.xlsx)", gerar_excel({"Por coletor": comp["por_coletor"], "Saíram": comp["saiu"],
                                                           "Entraram": comp["entrou"], "Trocaram": comp["trocou"]}),
                 f"acompanhamento_{empresa}_{atual}.xlsx", chave="acomp_baixar")
    st.caption("⚠️ “Saíram da lista” é o melhor indicador que a planilha permite, mas não prova coleta: a OS pode ter sido "
               "cancelada ou encerrada na plataforma.")
    with st.expander("📈 Produtividade dos últimos dias"):
        if st.button("Calcular histórico", key="acomp_hist"):
            por_data = {d: repo.ler_snapshot(sb, empresa, d) for d in datas}
            st.session_state["acomp_prod"] = acompanhamento.produtividade(por_data)
        prod = st.session_state.get("acomp_prod")
        if prod is not None and not prod.empty:
            st.bar_chart(prod)
            st.dataframe(prod, use_container_width=True)
    for titulo, chave_df in (("Saíram da lista", "saiu"), ("Entraram", "entrou"), ("Trocaram de coletor", "trocou")):
        if len(comp[chave_df]):
            with st.expander(f"{titulo} ({len(comp[chave_df])})"):
                st.dataframe(comp[chave_df], hide_index=True, use_container_width=True)


# ===================================================================================== COLETORES
def _novo_coletor(sb, usuarios):
    ctr = st.session_state.setdefault("rota_novo_ctr", 0)
    livres = {u["id"]: f"{u['nome_completo']} ({u['usuario']})" for u in usuarios if u.get("cargo") == "COLETOR"}
    with cartao():
        st.markdown("**➕ Novo coletor**")
        nome = st.text_input("Nome na rota (ex.: GEOVAN)", key=f"rc_nome_{ctr}")
        telefone = st.text_input("WhatsApp (opcional, com DDD)", key=f"rc_tel_{ctr}")
        tipo = st.selectbox("Tipo", nomes.TIPOS, format_func=nomes.ROTULO_TIPO.get, key=f"rc_tipo_{ctr}",
                            help="Retentativas: recebe as OS que já foram à rua. Depósito: guarda OS que você não consegue "
                                 "tirar da plataforma; não recebe rota no WhatsApp.")
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
            repo.criar_coletor(sb, nome, pr.numero_whatsapp(telefone), usuario_id, tipo)
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
        st.dataframe([{"Nome na rota": c["nome_rota"], "Tipo": nomes.ROTULO_TIPO.get(c.get("tipo") or "normal", "—"),
                       "Login": rotulo_login(c.get("usuario_id")),
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
            tipo_atual = c.get("tipo") or "normal"
            tipo = st.selectbox("Tipo", nomes.TIPOS, index=nomes.TIPOS.index(tipo_atual) if tipo_atual in nomes.TIPOS else 0,
                                format_func=nomes.ROTULO_TIPO.get, key=f"rce_tipo_{escolhido}")
            ativo = st.checkbox("Ativo (aparece na hora de gerar rotas)", value=c["ativo"], key=f"rce_at_{escolhido}")
            if st.button("💾 Salvar alterações", key=f"rce_ok_{escolhido}"):
                campos = {"telefone": pr.numero_whatsapp(telefone), "usuario_id": login, "ativo": ativo}
                if tipo != tipo_atual:
                    campos["tipo"] = tipo
                try:
                    repo.atualizar_coletor(sb, escolhido, **campos)
                except Exception as erro:
                    st.error(f"Não consegui salvar (rodou o `migracao_v4.sql`?): {erro}")
                    return
                st.toast("Coletor atualizado.", icon="✅")
                st.rerun()
        sugestoes = vinculos.sugerir_vinculos(lista, usuarios)
        if sugestoes:
            with st.expander(f"🪄 {len(sugestoes)} vínculo(s) sugerido(s) com logins que já existem"):
                por_id_rota = {c["id"]: c["nome_rota"] for c in lista}
                st.dataframe([{"Coletor de rota": por_id_rota[cid], "Login sugerido": rotulo_login(uid), "Semelhança": f"{int(n * 100)}%"}
                              for cid, uid, n in sugestoes], hide_index=True, use_container_width=True)
                if st.button("Aplicar todas as sugestões", key="rc_aplicar_sug"):
                    for cid, uid, _ in sugestoes:
                        repo.atualizar_coletor(sb, cid, usuario_id=uid)
                    st.toast("Vínculos aplicados.", icon="🔗")
                    st.rerun()


def _apelidos(sb, lista):
    """Nomes como aparecem nos relatórios das plataformas -> coletor da rota (o sistema também aprende na hora de gerar)."""
    with st.expander("🔤 Apelidos: como o nome aparece nos relatórios"):
        st.caption("O sistema já reconhece pelo primeiro nome (ex.: “GUILHERME SANTOS ARAUJO” → GUILHERME). Cadastre aqui só os "
                   "casos especiais, como um nome escrito diferente ou uma pessoa com dois nomes.")
        apelidos = repo.listar_apelidos(sb)
        for ap, rota in sorted(apelidos.items()):
            a, b = st.columns([5, 1])
            a.write(f"`{ap}` → **{rota}**")
            if b.button("Remover", key=f"ap_rm_{ap}"):
                repo.remover_apelido(sb, ap)
                st.rerun()
        c1, c2, c3 = st.columns([3, 2, 1])
        novo = c1.text_input("Nome no relatório", key="ap_novo", placeholder="Ex.: Arleide Santos da Siva")
        rota = c2.selectbox("Coletor da rota", [c["nome_rota"] for c in lista], index=None, placeholder="Escolha...", key="ap_rota")
        if c3.button("Salvar", key="ap_salvar", use_container_width=True):
            if novo.strip() and rota:
                try:
                    repo.salvar_apelido(sb, nomes.normalizar_nome(novo), rota)
                    st.rerun()
                except Exception as erro:
                    st.error(f"Não consegui salvar (rodou o `migracao_v4.sql`?): {erro}")
            else:
                st.error("Informe o nome e escolha o coletor.")


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
    _apelidos(sb, lista)


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
        # A chave inclui o arquivo: ao trocar a planilha de exemplo, as sugestões são refeitas.
        # (Antes, "rp_nome" era usada duas vezes — no nome da empresa e no campo "Nome do cliente" — e quebrava a tela.)
        sufixo_chave = f"{abs(hash((amostra.name, amostra.size))) % 100000}"
        for i, (campo, rotulo) in enumerate(pf.CAMPOS.items()):
            sugestao = pf.sugerir_coluna(campo, colunas) or "(não tem)"
            escolha = cols[i % 3].selectbox(rotulo, opcoes, index=opcoes.index(sugestao), key=f"rp_col_{campo}_{sufixo_chave}")
            mapa[campo] = None if escolha == "(não tem)" else escolha
        extras = {}
        with st.expander("➕ Colunas extras (opcional): coletor, agenda, prioridade, último motivo..."):
            st.caption("Servem para avisos e para separar por coletor. Se a planilha não tiver, deixe “(não tem)”.")
            cx = st.columns(3)
            achadas = {c.lower(): c for c in colunas}
            for i, (campo, rotulo) in enumerate(pf.EXTRAS.items()):
                esc = cx[i % 3].selectbox(rotulo, opcoes, index=opcoes.index(achadas.get(rotulo.split(" / ")[0].lower(), "(não tem)")),
                                          key=f"rpx_{campo}_{sufixo_chave}")
                extras[campo] = None if esc == "(não tem)" else esc
        if st.button("💾 Salvar empresa", type="primary", key="rp_salvar"):
            if not nome.strip():
                st.error("Informe o nome da empresa.")
            elif not (mapa["endereco"] and mapa["nome"]):
                st.error("Escolha pelo menos as colunas de nome do cliente e endereço.")
            else:
                try:
                    repo.salvar_perfil(sb, pf.perfil_a_partir_do_mapa(nome, sufixo, mapa, extras))
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
    {"🚚 Gerar e enviar": _gerar, "📊 Acompanhamento": _acompanhamento, "👷 Coletores": _coletores,
     "🏢 Empresas e grupos": _empresas, "📜 Histórico": _historico}[secao](sb)
