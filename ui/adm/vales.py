"""Vales (adiantamentos): lançar com foto do comprovante, consultar e corrigir."""
import streamlit as st

from core import armazenamento, auditoria, dados, sessao
from core import financeiro as fin
from core import leitor_comprovante as leitor
from core.config import cfg
from core.utils import brl, data_br, hoje_br
from disparador import ia
from rotas import repositorio as rotas_repo
from rotas.nomes import casar
from ui.componentes import cabecalho, cartao, confirmar, erro_banco, metricas, mostrar_foto, vazio


def _assinatura(arquivo):
    """Identifica a foto escolhida (para a leitura da IA não valer para outra foto)."""
    return f"{getattr(arquivo, 'name', '')}|{getattr(arquivo, 'size', '')}"


def _duplicado(sb, id_transacao):
    """Vale já lançado com o mesmo código de transação (None se não houver ou se a coluna ainda não existe: migracao_v8.sql)."""
    if not id_transacao:
        return None
    try:
        achados = sb.table("vales_coleta").select("id,data,coletor,valor_vale").eq("comprovante_id", id_transacao).limit(1).execute().data
    except Exception:  # noqa: BLE001 — sem a coluna a checagem só deixa de existir
        return None
    return achados[0] if achados else None


def _ler_com_ia(sb, foto, coletores):
    """Lê o comprovante com o Gemini e guarda a leitura conferida na sessão (o formulário usa como sugestão)."""
    chave = cfg("GEMINI_API_KEY")
    if not chave:
        st.info("Para ler o comprovante com IA, configure `GEMINI_API_KEY` nos secrets (chave grátis em aistudio.google.com).")
        return
    if st.button("🤖 Ler comprovante com IA", key="vale_ler"):
        try:
            with st.spinner("Lendo o comprovante..."):
                imagem = armazenamento.processar_imagem(armazenamento.ler_bytes(foto), 1280, 80)
                bruto = ia.ler_comprovante(chave, cfg("GEMINI_MODEL", ia.MODELO_PADRAO), imagem, leitor.PROMPT)
            leitura = leitor.interpretar(bruto, hoje_br())
            leitura["coletor"], leitura["origem"] = (None, "")
            if leitura["nome"]:
                leitura["coletor"], leitura["origem"] = casar(leitura["nome"], coletores, rotas_repo.listar_apelidos(sb))
            achado = _duplicado(sb, leitura["id_transacao"])
            if achado:
                leitura["avisos"].append(f"⚠️ Este comprovante já foi lançado: {data_br(achado['data'])} · {achado['coletor']} · {brl(achado['valor_vale'])}.")
                leitura["duplicado"] = True
            leitura["arquivo"] = _assinatura(foto)
            st.session_state["vale_ia"] = leitura
            st.session_state["vale_form"] = st.session_state.get("vale_form", 0) + 1  # recria os campos já preenchidos
        except (ia.ErroIA, ValueError) as erro:
            st.warning(f"Não consegui ler o comprovante ({erro}). Preencha à mão.")
    st.caption("A imagem é enviada ao Google (Gemini) só para leitura. A IA apenas sugere: confira os campos antes de lançar.")


def _formulario(sb, coletores):
    usuario = sessao.usuario_atual()["usuario"]
    with cartao():
        st.markdown("**➕ Lançar novo vale**")
        if not coletores:
            vazio("Nenhum coletor cadastrado.")
            return
        foto = st.file_uploader("Foto do comprovante", type=["png", "jpg", "jpeg"], key=f"vale_foto_{st.session_state.get('vale_up', 0)}")
        if foto:
            _ler_com_ia(sb, foto, coletores)
        leitura = st.session_state.get("vale_ia") if foto else None
        if leitura and leitura.get("arquivo") != _assinatura(foto):
            leitura = None  # leitura de outra foto
        padrao_coletor = leitura.get("coletor") if leitura else None
        if leitura:
            partes = [f"valor **{brl(leitura['valor'])}**" if leitura.get("valor") else "valor não lido",
                      f"data **{data_br(leitura['data'])}**" if leitura.get("data") else "data não lida",
                      f"recebedor lido: **{leitura['nome'] or '—'}**"]
            partes.append(f"→ coletor **{padrao_coletor}** ({leitura['origem']})" if padrao_coletor
                          else "→ coletor não identificado: escolha abaixo")
            st.success("🤖 Leitura da IA: " + " · ".join(partes))
            for aviso in leitura["avisos"]:
                st.warning(aviso)
        n = st.session_state.get("vale_form", 0)
        with st.form("form_vale", clear_on_submit=True):
            coletor = st.selectbox("Coletor", coletores, key=f"vale_coletor_{n}",
                                   index=coletores.index(padrao_coletor) if padrao_coletor in coletores else 0)
            valor = st.number_input("Valor (R$)", min_value=0.01, step=5.0, key=f"vale_valor_{n}", format="%.2f",
                                    value=float(leitura["valor"]) if leitura and leitura.get("valor") else 10.0)
            data = st.date_input("Data", key=f"vale_data_{n}", format="DD/MM/YYYY",
                                 value=leitura["data"] if leitura and leitura.get("data") else hoje_br())
            motivo = st.text_input("Motivo (opcional)", value="Adiantamento de Coletas", key=f"vale_motivo_{n}")
            mesmo_assim = st.checkbox("Lançar mesmo assim (comprovante repetido)", key=f"vale_dup_{n}") if leitura and leitura.get("duplicado") else True
            enviar = st.form_submit_button("Lançar vale", type="primary", use_container_width=True)
        if not enviar:
            return
        if not foto:
            st.error("Adicione a foto do comprovante antes de lançar.")
            return
        if not mesmo_assim:
            st.error("Este comprovante já foi lançado. Marque \"Lançar mesmo assim\" se for outro pagamento.")
            return
        id_transacao = leitura.get("id_transacao") if leitura else None
        try:
            with st.spinner("Salvando..."):
                caminho = armazenamento.salvar_foto(sb, foto, f"vale_{usuario}")
                linha = {"data": str(data), "coletor": coletor, "valor_vale": round(float(valor), 2),
                         "descricao": motivo.strip(), "foto_url": caminho}
                try:
                    sb.table("vales_coleta").insert({**linha, "comprovante_id": id_transacao} if id_transacao else linha).execute()
                except Exception as erro:  # noqa: BLE001 — coluna nova ainda não criada (migracao_v8.sql): lança sem o código
                    if id_transacao and "comprovante_id" in str(erro):
                        sb.table("vales_coleta").insert(linha).execute()
                    else:
                        raise
            auditoria.registrar(sb, usuario, "vale_lancado", f"{coletor} {brl(valor)} em {data}" + (" (leitura por IA)" if leitura else ""))
            dados.invalidar()
            st.session_state["vale_up"] = st.session_state.get("vale_up", 0) + 1  # limpa o campo da foto
            st.session_state.pop("vale_ia", None)
            st.toast(f"Vale de {brl(valor)} lançado.", icon="✅")
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))
        except Exception as erro:
            st.error(f"Erro ao salvar o vale: {erro}")


def _historico(sb, vales):
    usuario = sessao.usuario_atual()["usuario"]
    with cartao():
        st.markdown("**📋 Vales do período**")
        if vales.empty:
            vazio("Nenhum vale encontrado para os filtros.")
            return
        ordenados = vales.sort_values(["data", "id"], ascending=False)
        metricas([("Quantidade", f"{len(ordenados)}"), ("Total em vales", brl(ordenados["valor_vale"].sum()))])
        tabela = ordenados[["data", "coletor", "valor_vale", "descricao"]].copy()
        tabela["data"] = tabela["data"].map(data_br)
        st.dataframe(fin.formatar_moeda(tabela.rename(columns={
            "data": "Data", "coletor": "Coletor", "valor_vale": "Valor", "descricao": "Motivo"}), ["Valor"]),
            hide_index=True, use_container_width=True)

        rotulos = {int(r.id): f"{data_br(r.data)} · {r.coletor} · {brl(r.valor_vale)}" for r in ordenados.head(200).itertuples()}
        escolhido = st.selectbox("Ver comprovante / corrigir", list(rotulos), format_func=rotulos.get,
                                 index=None, placeholder="Escolha um vale...")
        if escolhido is None:
            return
        linha = ordenados[ordenados["id"] == escolhido].iloc[0]
        mostrar_foto(sb, linha["foto_url"], largura=260, legenda="Comprovante do vale", miniatura=True, chave=f"vale_{escolhido}")
        with st.expander("🗑️ Excluir este vale (lançado por engano)"):
            if confirmar("Confirmo a exclusão", f"chk_del_vale_{escolhido}") and st.button("Excluir vale", key=f"del_vale_{escolhido}"):
                sb.table("vales_coleta").delete().eq("id", int(escolhido)).execute()
                auditoria.registrar(sb, usuario, "vale_excluido", rotulos[escolhido])
                dados.invalidar()
                st.toast("Vale excluído.", icon="🗑️")
                st.rerun()


def render(sb, filtro):
    try:
        _, vales, _, _ = dados.carregar_financeiro(sb, filtro.ini, filtro.fim, filtro.coletor)
        coletores = dados.nomes_coletores(sb)
    except Exception as erro:
        erro_banco(erro)
        return
    cabecalho("📉 Vales", filtro.descricao)
    esquerda, direita = st.columns([2, 3])
    with esquerda:
        _formulario(sb, coletores)
    with direita:
        _historico(sb, vales)
