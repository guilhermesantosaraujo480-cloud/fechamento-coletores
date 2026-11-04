"""Rede de segurança do site: qualquer erro inesperado vira uma mensagem calma com código de referência, nunca um erro técnico."""
import sys
import traceback
import uuid

import streamlit as st

from core import sessao


def codigo_de_erro():
    return uuid.uuid4().hex[:6].upper()


def local_do_erro(erro, quantos=3):
    """Últimas linhas do código do projeto por onde o erro passou (ex.: 'app.py:120 _executar > core/sessao.py:30 restaurar')."""
    try:
        quadros = [q for q in traceback.extract_tb(erro.__traceback__) if "site-packages" not in q.filename]
        return " > ".join(f"{q.filename.split('fechamento-coletores/')[-1].split('/mount/src/')[-1]}:{q.lineno} {q.name}" for q in quadros[-quantos:])
    except Exception:  # noqa: BLE001
        return ""


def mostrar_falha(sb, erro):
    """Mostra a mensagem amigável (detalhe técnico só para o administrador), registra no log do servidor e na auditoria."""
    codigo = codigo_de_erro()
    traceback.print_exception(type(erro), erro, erro.__traceback__, file=sys.stderr)
    print(f"[falha {codigo}] {type(erro).__name__}", file=sys.stderr)
    try:
        from core import auditoria
        u = sessao.usuario_atual() or {}
        auditoria.registrar(sb, u.get("usuario", "?"), "falha_inesperada", f"{codigo} {type(erro).__name__}: {str(erro)[:120]} @ {local_do_erro(erro)}"[:500])
    except Exception:  # noqa: BLE001 — o registro é secundário
        pass
    st.warning("Algo não saiu como esperado, provavelmente uma oscilação de internet. Nada foi perdido: toque em **Tentar novamente**. "
               f"Se continuar, avise o administrador e informe o código **{codigo}**.")
    if sessao.eh_adm():
        with st.expander("Detalhe técnico (só administrador)"):
            st.code(f"{type(erro).__name__}: {erro}", language="text")
    if st.button("Tentar novamente", type="primary", key=f"tentar_{codigo}"):
        st.rerun()
    return codigo


def rodar_protegido(executar, obter_sb=None, plano_b=None):
    """Roda `executar()`. Exceções de controle do Streamlit (rerun/stop) passam; qualquer outra vira mensagem amigável."""
    try:
        executar()
    except Exception as erro:  # noqa: BLE001 — Rerun/Stop do Streamlit herdam de BaseException e não caem aqui
        sb = None
        try:
            sb = obter_sb() if obter_sb else None
        except Exception:  # noqa: BLE001
            sb = None
        mostrar_falha(sb, erro)
        if plano_b:
            try:
                plano_b(lambda: sb)
            except Exception:  # noqa: BLE001 — o plano B é só um reforço
                pass
