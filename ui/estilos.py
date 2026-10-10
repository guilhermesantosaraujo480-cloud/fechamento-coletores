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
@media (max-width: 640px) {
    .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
    [data-testid="stMetricValue"] { font-size: 1.25rem; }
}
</style>
"""


def aplicar():
    st.markdown(CSS, unsafe_allow_html=True)
