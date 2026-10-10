"""Coletor envia a foto do comprovante e a quantidade de aparelhos."""
import hashlib

import streamlit as st

from core import armazenamento, dados, sessao
from core.config import valor_por_coleta
from core.consulta import buscar_todos
from core.utils import agora_br, brl, data_br
from ui.componentes import cabecalho, cartao

ROTULO_STATUS = {"Aprovado": "🟢 Aprovada", "Pendente": "🟡 Aguardando", "Recusado": "🔴 Recusada"}
MAX_APARELHOS = 500


def _ultimos(sb, nome):
    try:
        linhas = (sb.table("coletas").select("id,data,quantidade,valor_total,status")
                    .eq("coletor", nome).order("id", desc=True).limit(8).execute().data) or []
    except Exception:
        return
    with cartao():
        st.markdown("**🕘 Seus últimos envios**")
        if not linhas:
            st.caption("Você ainda não enviou nenhuma coleta.")
        for r in linhas:
            st.write(f"{data_br(r['data'])} · {r['quantidade']} un · {brl(r['valor_total'])} · "
                     f"{ROTULO_STATUS.get(r['status'], r['status'])}")


def render(sb):
    u = sessao.usuario_atual()
    nome = u["nome_completo"]
    cabecalho("📲 Enviar coleta", f"Registrando para **{nome}**")
    ctr = st.session_state.setdefault("reset_envio", 0)

    esquerda, direita = st.columns([3, 2])
    with esquerda:
        with cartao():
            quantidade = st.number_input("Quantidade de aparelhos", min_value=1, max_value=MAX_APARELHOS,
                                         step=1, value=1, key=f"qtd_{ctr}")
            foto = st.file_uploader("Foto do comprovante (tire agora ou escolha da galeria)",
                                    type=["png", "jpg", "jpeg"], key=f"foto_{ctr}")
            if foto:
                st.image(foto, width=240, caption="Confira se a foto está legível")
            st.caption(f"Valor estimado: **{brl(quantidade * valor_por_coleta())}** (após aprovação)")
            enviar = st.button("Enviar para aprovação", type="primary", use_container_width=True, disabled=foto is None)

        if enviar and foto:
            conteudo = armazenamento.ler_bytes(foto)
            impressao = hashlib.sha1(conteudo).hexdigest()
            if st.session_state.get("ultima_foto") == impressao:
                st.warning("Essa foto já foi enviada. Se for outra coleta, tire uma nova foto.")
            else:
                try:
                    with st.spinner("Enviando..."):
                        caminho = armazenamento.salvar_foto(sb, conteudo, f"coleta_{u['usuario']}")
                        sb.table("coletas").insert({
                            "data": agora_br().strftime("%Y-%m-%d"), "coletor": nome, "quantidade": int(quantidade),
                            "foto_url": caminho, "status": "Pendente", "pago": False,
                            "valor_total": round(float(quantidade) * valor_por_coleta(), 2),
                        }).execute()
                    st.session_state["ultima_foto"] = impressao
                    st.session_state["reset_envio"] = ctr + 1
                    dados.invalidar()
                    st.toast("Envio realizado! Agora é só aguardar a aprovação.", icon="✅")
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))
                except Exception as erro:
                    st.error(f"Erro no envio: {erro}")
    with direita:
        _ultimos(sb, nome)
