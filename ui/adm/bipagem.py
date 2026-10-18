"""Bipagem: prepara o lote (PDF -> seriais), coloca na fila e acompanha. Quem executa é o agente local."""
import hashlib
from io import BytesIO

import pandas as pd
import streamlit as st

from bipagem import extracao, fila
from bipagem.regras import EQUIPAMENTOS, pontos
from core import auditoria, sessao
from core.exportacao import gerar_excel
from ui.componentes import baixar_excel, cabecalho, cartao, confirmar, metricas, navegacao, vazio

SECOES = ["🆕 Novo lote", "📋 Lotes"]


def _status_agente(sb):
    try:
        online, info, _ = fila.agente_online(sb)
    except Exception as erro:
        st.error(f"Não consegui ler a fila da bipagem (rodou o `migracao_v5.sql`?): {erro}")
        return None
    if online:
        st.success(f"🟢 Agente ligado no seu computador ({info or 'pronto'}).")
    else:
        st.warning("🔴 Agente desligado. No seu computador, abra o **iniciar_agente.bat** (ou rode "
                   "`python -m bipagem.agente`). O lote fica na fila e começa assim que ele ligar.")
    return online


def _ler_arquivo(arquivo):
    """(registros|None, seriais, resumo|None). PDF -> extrai com a OS e a página; planilha -> só os seriais.
    O resultado fica guardado na sessão para não reler o PDF a cada clique."""
    bruto = arquivo.getvalue()
    chave = f"bip_{arquivo.name}_{len(bruto)}_{hashlib.md5(bruto[:4096]).hexdigest()}"
    if chave in st.session_state:
        return st.session_state[chave]
    if arquivo.name.lower().endswith(".pdf"):
        barra = st.progress(0.0, text="Lendo o PDF…")
        registros = extracao.extrair_pdf(BytesIO(bruto), lambda p, t: barra.progress(p / t, text=f"Página {p} de {t}"))
        barra.empty()
        resultado = (registros, extracao.seriais_unicos(registros), extracao.resumir(registros))
    else:
        seriais = extracao.ler_planilha(BytesIO(bruto))
        resultado = (None, seriais, None)
    st.session_state[chave] = resultado
    return resultado


def _novo_lote(sb):
    st.caption("Envie o **PDF das ordens de serviço** (o mesmo do localizador) ou a planilha de seriais "
               "(`Os_automação.xlsx`, coluna Numero).")
    arquivo = st.file_uploader("PDF ou planilha", type=["pdf", "xlsx", "xls"], key="bip_arquivo")
    if arquivo is None:
        return
    try:
        registros, seriais, resumo = _ler_arquivo(arquivo)
    except Exception as erro:
        st.error(f"Não consegui ler o arquivo: {erro}")
        return
    if not seriais:
        st.error("Nenhum serial encontrado nesse arquivo.")
        return

    if resumo:
        metricas([("📄 OS no PDF", f"{resumo['paginas']}"), ("🔢 Seriais únicos", f"{resumo['seriais']}"),
                  ("⚠️ OS sem serial", f"{len(resumo['sem_serial'])}"),
                  ("🔁 Seriais repetidos", f"{len(resumo['repetidos'])}")])
        if resumo["sem_serial"]:
            with st.expander(f"OS sem serial no PDF ({len(resumo['sem_serial'])})"):
                st.dataframe(pd.DataFrame(resumo["sem_serial"])[["pagina", "os"]].rename(
                    columns={"pagina": "Página", "os": "OS"}), hide_index=True, use_container_width=True)
                st.caption("Elas serão bipadas normalmente: o robô usa o próximo serial da lista (e o ponto, se preciso).")
        if resumo["repetidos"]:
            with st.expander(f"Seriais que aparecem em mais de uma OS ({len(resumo['repetidos'])})"):
                st.dataframe(pd.DataFrame([{"Serial": s, "OS": ", ".join(o)} for s, o in resumo["repetidos"].items()]),
                             hide_index=True, use_container_width=True)
    else:
        metricas([("🔢 Seriais na planilha", f"{len(seriais)}")])
    baixar_excel("⬇️ Baixar a lista de seriais (Os_automação.xlsx)",
                 gerar_excel({"Hoja1": pd.DataFrame({"Numero": seriais})}), "Os_automação.xlsx", "bip_baixar")

    st.markdown("##### Configuração do lote")
    nome = st.text_input("Nome do lote", value=f"Bipagem {pd.Timestamp.now(tz='America/Sao_Paulo'):%d/%m %H:%M}", key="bip_nome")
    c1, c2 = st.columns(2)
    qtd = int(st.radio("Aparelhos por OS", [1, 2], horizontal=True, key="bip_qtd"))
    padrao_ordens = max(resumo["paginas"] if resumo else len(seriais) // qtd, 1)
    ordens = int(c2.number_input("Quantas ordens bipar", min_value=1, max_value=5000, value=padrao_ordens, step=1,
                                 key=f"bip_ordens_{padrao_ordens}_{qtd}"))
    opcoes = list(EQUIPAMENTOS)
    equip1 = c1.selectbox("Tipo do 1º aparelho", opcoes, key="bip_eq1")
    equip2 = c2.selectbox("Tipo do 2º aparelho", opcoes, key="bip_eq2") if qtd == 2 else None

    precisa = ordens * qtd
    if precisa > len(seriais):
        st.info(f"Serão usados {precisa} seriais e a lista tem {len(seriais)}: depois do último, o robô recomeça a lista "
                "com um ponto no fim (e mais pontos se a plataforma recusar de novo).")
    st.caption("O ponto também é acrescentado na hora, sozinho, sempre que a plataforma recusar um serial como duplicado.")

    if confirmar("Conferi: o agente vai ENCERRAR ordens de verdade na Reintegra com esses dados", "bip_confirma"):
        if ordens > 1:
            st.caption("💡 Na primeira vez, ou depois de qualquer mudança na plataforma, faça um lote de **1 ordem** e acompanhe.")
        if st.button("📥 Colocar na fila", type="primary", use_container_width=True, key="bip_enfileirar"):
            try:
                lote = fila.criar_lote(sb, sessao.usuario_atual()["usuario"], nome, seriais, qtd, equip1, equip2, ordens)
                auditoria.registrar(sb, sessao.usuario_atual()["usuario"], "bipagem_lote",
                                    f"lote={lote['id']} ordens={ordens} aparelhos={qtd} {equip1}/{equip2}")
            except Exception as erro:
                st.error(f"Não foi possível criar o lote (rodou o `migracao_v5.sql`?): {erro}")
                return
            st.success(f"✅ Lote #{lote['id']} na fila. Acompanhe em **📋 Lotes**.")


def _cartao_lote(sb, l):
    with cartao():
        total = max(l["limite_ordens"], 1)
        st.markdown(f"**#{l['id']} · {l['nome']}** — {fila.ROTULO.get(l['status'], l['status'])}")
        st.progress(min(l["ordens_ok"] / total, 1.0), text=f"{l['ordens_ok']} de {l['limite_ordens']} ordens bipadas"
                    + (f" · ⚠️ {l['ordens_erro']} para conferir" if l["ordens_erro"] else ""))
        equip = l["equip1"] + (f" + {l['equip2']}" if l["qtd_aparelhos"] == 2 else "")
        st.caption(f"{l['qtd_aparelhos']} aparelho(s) por OS · {equip} · criado por {l.get('criado_por') or '—'}"
                   + (f" · agente {l['agente']}" if l.get("agente") else ""))
        if l.get("mensagem"):
            st.caption(f"ℹ️ {l['mensagem']}")
        c1, c2, c3 = st.columns(3)
        if l["status"] in ("pendente", "executando"):
            if c1.button("🛑 Parar" if l["status"] == "executando" else "🚫 Cancelar", key=f"bp_parar_{l['id']}",
                         use_container_width=True):
                fila.pedir_parada(sb, l["id"])
                st.rerun()
        if l["status"] in ("parado", "erro"):
            if c1.button("▶️ Retomar", key=f"bp_ret_{l['id']}", use_container_width=True):
                fila.retomar(sb, l["id"])
                st.rerun()
        with st.expander("Ver as OS deste lote"):
            try:
                linhas = fila.itens(sb, l["id"])
            except Exception as erro:
                st.error(str(erro))
                return
            if not linhas:
                st.caption("Nenhuma OS processada ainda.")
                return
            tabela = pd.DataFrame(linhas)[["os", "status", "serial1", "serial2", "tentativas", "obs"]]
            tabela.columns = ["OS", "Status", "Serial 1", "Serial 2", "Tentativas", "Obs"]
            st.dataframe(tabela, hide_index=True, use_container_width=True)
            st.download_button("⬇️ Baixar resultado (CSV)", tabela.to_csv(index=False, sep=";").encode("utf-8-sig"),
                               f"bipagem_lote_{l['id']}.csv", "text/csv", key=f"bp_csv_{l['id']}")


def _lotes(sb):
    st.button("🔄 Atualizar", key="bip_atualizar")
    try:
        lotes = fila.listar_lotes(sb)
    except Exception as erro:
        st.error(f"Não foi possível ler os lotes (rodou o `migracao_v5.sql`?): {erro}")
        return
    if not lotes:
        vazio("Nenhum lote ainda. Em **🆕 Novo lote**, envie o PDF.")
        return
    if any(l["status"] in fila.STATUS_ATIVOS for l in lotes):
        st.caption("Clique em 🔄 Atualizar para ver o andamento.")
    for l in lotes:
        _cartao_lote(sb, l)


def render(sb):
    cabecalho("🔖 Bipagem de aparelhos", "Reintegra · o navegador roda no seu computador (agente local)")
    _status_agente(sb)
    secao = navegacao(SECOES, "nav_bipagem")
    if secao == SECOES[0]:
        _novo_lote(sb)
    else:
        _lotes(sb)
