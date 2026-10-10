"""Testes (unittest). Rodar: python -m unittest discover -s tests -t . -v

Em ambientes sem `bcrypt`, `streamlit` ou `supabase` instalados, os testes usam substitutos simples (fakes).
"""
import hashlib
import os
import sys
import types

try:
    import bcrypt  # noqa: F401
except Exception:  # substituto só para testes (NÃO é criptografia de verdade)
    stub = types.ModuleType("bcrypt")

    def _hashpw(senha, sal):
        return b"$2b$12$" + hashlib.sha256(sal + senha).hexdigest().encode() + b"|" + sal

    def _checkpw(senha, hashed):
        sal = hashed.split(b"|", 1)[1]
        return hashed == _hashpw(senha, sal)

    stub.gensalt = lambda: os.urandom(4).hex().encode()
    stub.hashpw = _hashpw
    stub.checkpw = _checkpw
    sys.modules["bcrypt"] = stub
