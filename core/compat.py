"""Compatibilidade com versões novas do Streamlit.

O Streamlit está trocando `use_container_width=True` por `width="stretch"` e avisou que o parâmetro antigo seria removido.
Em vez de editar dezenas de chamadas (e correr o risco de quebrar versões antigas), este módulo olha a assinatura de
cada função instalada: se ela AINDA aceita `use_container_width`, nada muda; se não aceita mais, o pedido é traduzido
para `width="stretch"` (ou "content"). Assim o app funciona tanto na versão que você usa hoje quanto numa futura.
"""
import functools
import inspect

NOMES = ("button", "download_button", "link_button", "form_submit_button", "dataframe", "data_editor", "table",
         "image", "plotly_chart", "altair_chart", "pyplot", "pydeck_chart", "vega_lite_chart", "bar_chart", "line_chart",
         "area_chart", "scatter_chart", "map", "page_link")


def _aceita(funcao, parametro):
    try:
        params = inspect.signature(funcao).parameters
    except (TypeError, ValueError):
        return True  # não dá para saber: não mexe
    return parametro in params


def _traduzir(funcao):
    """Embrulha `funcao` para trocar use_container_width por width. Devolve a própria função se não for preciso."""
    if _aceita(funcao, "use_container_width") or not _aceita(funcao, "width"):
        return funcao

    @functools.wraps(funcao)
    def nova(*args, **kwargs):
        if "use_container_width" in kwargs:
            largo = kwargs.pop("use_container_width")
            if largo is not None and "width" not in kwargs:
                kwargs["width"] = "stretch" if largo else "content"
        return funcao(*args, **kwargs)
    nova._compat = True
    return nova


def instalar(st, delta_generator=None):
    """Aplica a tradução em `st` (e na classe DeltaGenerator, usada por colunas, sidebar e containers).
    Devolve a lista de nomes que precisaram de tradução (vazia = versão antiga, nada foi alterado)."""
    trocados = []
    if delta_generator is None:
        try:
            from streamlit.delta_generator import DeltaGenerator as delta_generator
        except Exception:  # noqa: BLE001
            delta_generator = None
    for nome in NOMES:
        original = getattr(st, nome, None)
        if original is not None and not getattr(original, "_compat", False):
            novo = _traduzir(original)
            if novo is not original:
                setattr(st, nome, novo)
                trocados.append(nome)
        if delta_generator is not None:
            metodo = getattr(delta_generator, nome, None)
            if metodo is not None and not getattr(metodo, "_compat", False):
                novo = _traduzir(metodo)
                if novo is not metodo:
                    try:
                        setattr(delta_generator, nome, novo)
                        if nome not in trocados:
                            trocados.append(nome)
                    except (AttributeError, TypeError):
                        pass
    return trocados
