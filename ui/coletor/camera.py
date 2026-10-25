"""Câmera "leve": o próprio celular reduz a foto (1280 px, JPEG) ANTES de enviar. Gasta bem menos internet e memória.

É opcional: só aparece se o secret FOTO_LEVE estiver ligado ("sim"). O envio do jeito normal continua disponível.
O componente é uma página HTML simples (pasta camera_leve/), sem biblioteca externa nem instalação.
"""
import base64
import binascii
import os

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_leve")
_componente = None


def ligada(cfg):
    return str(cfg("FOTO_LEVE", "")).strip().lower() in ("1", "sim", "true", "ligado", "on")


def decodificar(valor):
    """Valor devolvido pelo componente -> bytes do JPEG (ou None se vier vazio/estragado)."""
    if not isinstance(valor, dict) or not valor.get("b64"):
        return None
    try:
        return base64.b64decode(valor["b64"], validate=True)
    except (binascii.Error, ValueError):
        return None


def camera_leve(chave):
    """Mostra o botão da câmera e devolve os bytes da foto já reduzida (ou None enquanto não houver foto)."""
    global _componente
    try:
        import streamlit.components.v1 as components

        if _componente is None:
            _componente = components.declare_component("camera_leve", path=PASTA)
        return decodificar(_componente(key=chave, default=None))
    except Exception:  # noqa: BLE001 — se o componente falhar, o envio normal continua funcionando
        return None
