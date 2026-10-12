"""Sugere qual login (usuário COLETOR) corresponde a cada nome de rota."""
import difflib
import re
import unicodedata


def _norm(texto):
    sem = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", sem).strip()


def sugerir_vinculos(coletores_rota, usuarios, minimo=0.6):
    """[(id_coletor_rota, id_usuario, nota)] só para coletores ainda sem login. Um login não é sugerido duas vezes."""
    ja_usados = {c["usuario_id"] for c in coletores_rota if c.get("usuario_id")}
    candidatos = [u for u in usuarios if u.get("cargo") == "COLETOR" and u["id"] not in ja_usados]
    pares = []
    for c in coletores_rota:
        if c.get("usuario_id"):
            continue
        nome = _norm(c["nome_rota"])
        for u in candidatos:
            alvos = [_norm(u["nome_completo"]), _norm(u["usuario"])]
            nota = max(difflib.SequenceMatcher(None, nome, a).ratio() for a in alvos)
            if nome.split()[:1] == _norm(u["nome_completo"]).split()[:1] and nome:
                nota = max(nota, 0.85)  # mesmo primeiro nome
            if nota >= minimo:
                pares.append((nota, c["id"], u["id"]))
    usados_c, usados_u, saida = set(), set(), []
    for nota, cid, uid in sorted(pares, reverse=True):
        if cid not in usados_c and uid not in usados_u:
            saida.append((cid, uid, round(nota, 2)))
            usados_c.add(cid)
            usados_u.add(uid)
    return saida
