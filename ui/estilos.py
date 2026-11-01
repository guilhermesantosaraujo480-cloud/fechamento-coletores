"""Ajustes visuais leves (CSS) para deixar o layout mais aproveitado e legível."""
import streamlit as st

CSS = """
<style>
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1400px; }
[data-testid="stMetric"] {
    background: rgba(102, 0, 153, 0.05);
    border: 1px solid rgba(102, 0, 153, 0.18);
    border-radius: 12px;
    padding: 0.7rem 0.9rem;
}
[data-testid="stMetricLabel"] p { font-size: 0.82rem; opacity: 0.8; }
[data-testid="stMetricValue"] { font-size: 1.55rem; }
h1, h2, h3 { letter-spacing: -0.01em; }
div.stButton > button, div.stDownloadButton > button, a[data-testid="stBaseLinkButton-secondary"] {
    border-radius: 10px;
}
img { max-width: 100%; height: auto; }
/* trava sutil: enquanto o app recalcula depois de um clique, o que está atualizando não aceita novo clique (evita duplo clique) */
[data-stale="true"] button, [data-stale="true"] a, [data-stale="true"] input, [data-stale="true"] [role="button"] {
    pointer-events: none !important;
}
/* resposta tátil no clique, sem animação pesada */
div.stButton > button, div.stDownloadButton > button { transition: transform .08s ease, box-shadow .15s ease, background-color .15s ease; }
div.stButton > button:active, div.stDownloadButton > button:active { transform: scale(.98); }
/* acessibilidade: foco visível para quem navega pelo teclado */
button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible, [role="tab"]:focus-visible,
[data-baseweb="select"]:focus-within { outline: 2px solid #660099 !important; outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
@media (max-width: 640px) {
    .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
    [data-testid="stMetricValue"] { font-size: 1.25rem; }
    /* celular: botões fáceis de tocar e campos que não dão "zoom" automático no iPhone */
    div.stButton > button, div.stDownloadButton > button { min-height: 2.9rem; }
    input, textarea, [data-baseweb="select"] { font-size: 16px !important; }
}
</style>
"""


def aplicar():
    st.markdown(CSS, unsafe_allow_html=True)
