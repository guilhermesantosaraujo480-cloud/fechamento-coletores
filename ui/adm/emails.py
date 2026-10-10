"""Página do disparador de e-mails (a lógica fica no pacote `disparador`)."""
from disparador.ui import renderizar_disparador


def render(sb):
    renderizar_disparador(sb)
