"""Utilitários de e-mail."""
import html
import re

EMAILS_FICTICIOS = {
    "email@email.com", "teste@teste.com", "naotem@naotem.com",
    "sememail@sememail.com", "cliente@cliente.com", "xxx@xxx.com",
}
_PADRAO_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def email_valido(email):
    email = (email or "").strip().lower()
    if not email or email in EMAILS_FICTICIOS or email.startswith("email@"):
        return False
    return _PADRAO_EMAIL.fullmatch(email) is not None


def html_para_texto(texto):
    texto = re.sub(r"<br\s*/?>", "\n", texto, flags=re.I)
    texto = re.sub(r"<[^>]+>", "", texto)
    return html.unescape(texto).strip()


def separar_emails(texto):
    """'a@x.com; b@y.com\\nc@z.com' -> conjunto de e-mails válidos em minúsculas."""
    candidatos = {e.strip().lower() for e in re.split(r"[\s,;]+", texto or "") if e.strip()}
    return {e for e in candidatos if email_valido(e)}
