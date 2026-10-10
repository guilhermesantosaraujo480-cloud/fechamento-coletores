"""Envio por SMTP (Gmail) com conexão reaproveitada e rodízio de contas."""
import smtplib


def _abrir_gmail(email, senha):
    smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
    smtp.login(email, senha)
    return smtp


class GerenteSMTP:
    """Mantém uma conexão aberta por conta (logar a cada e-mail é lento e pode ser bloqueado)."""

    def __init__(self, fabrica=_abrir_gmail):
        self._fabrica = fabrica
        self.conexoes = {}

    def fechar_uma(self, email):
        smtp = self.conexoes.pop(email, None)
        if smtp:
            try:
                smtp.quit()
            except Exception:
                pass

    def fechar(self):
        for email in list(self.conexoes):
            self.fechar_uma(email)

    def enviar(self, conta, msg):
        email = conta["email"]
        for tentativa in range(2):
            try:
                smtp = self.conexoes.get(email)
                if smtp is None:
                    smtp = self._fabrica(email, conta["_senha"])
                    self.conexoes[email] = smtp
                smtp.send_message(msg)
                return
            except (smtplib.SMTPServerDisconnected, ConnectionError, OSError):
                self.fechar_uma(email)
                if tentativa == 1:
                    raise


def conta_esgotada(erro):
    """Erro de login/limite diário: a conta não deve mais ser usada nesta campanha."""
    t = str(erro).lower()
    return (isinstance(erro, smtplib.SMTPAuthenticationError)
            or "5.4.5" in t or "daily user sending" in t or "sending limit" in t)


def escolher_conta(contas, enviados_hoje, ponteiro):
    """Rodízio entre contas que ainda têm limite. Devolve (conta|None, novo_ponteiro)."""
    n = len(contas)
    for k in range(n):
        c = contas[(ponteiro + k) % n]
        if enviados_hoje.get(c["email"], 0) < int(c.get("limite_diario") or 0):
            return c, (ponteiro + k + 1) % n
    return None, ponteiro
