"""Criptografia das senhas de app (a chave fica nos secrets, nunca no banco)."""
PREFIXO = "enc:"

try:
    from cryptography.fernet import Fernet
except Exception:  # biblioteca não instalada
    Fernet = None


class Cofre:
    def __init__(self, chave):
        self._f = None
        if chave and Fernet is not None:
            try:
                self._f = Fernet(str(chave).encode())
            except Exception:
                self._f = None

    @property
    def ativo(self):
        return self._f is not None

    def proteger(self, senha):
        """Sem chave configurada devolve a senha pura (a interface avisa)."""
        if self._f is None:
            return senha
        return PREFIXO + self._f.encrypt(senha.encode()).decode()

    def revelar(self, valor):
        """Texto puro de volta; '' se não for possível (chave errada/ausente)."""
        if not valor:
            return ""
        valor = str(valor)
        if not valor.startswith(PREFIXO):
            return valor  # senha antiga ainda em texto puro
        if self._f is None:
            return ""
        try:
            return self._f.decrypt(valor[len(PREFIXO):].encode()).decode()
        except Exception:
            return ""

    @staticmethod
    def esta_protegida(valor):
        return str(valor or "").startswith(PREFIXO)
