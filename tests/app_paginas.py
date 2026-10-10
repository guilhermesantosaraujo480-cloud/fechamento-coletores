"""Lê a lista de páginas do app.py sem executá-lo."""
import ast


def paginas_adm():
    with open("app.py", encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    for no in arvore.body:
        if isinstance(no, ast.Assign) and getattr(no.targets[0], "id", "") == "PAGINAS_ADM":
            return [chave.value for chave in no.value.keys]
    raise AssertionError("PAGINAS_ADM não encontrado")
