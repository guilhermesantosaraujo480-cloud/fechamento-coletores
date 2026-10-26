"""Confere se os arquivos do projeto chegaram inteiros (nada vazio, nada trocado de lugar).

Uso (na pasta do projeto, só precisa do Python):   python verificar_projeto.py
Também roda sozinho no GitHub a cada envio (aba Actions > "Verificar arquivos") e acusa o problema por e-mail.

- ERRO  = arquivo vazio, arquivo com conteúdo de outro (ex.: texto do README dentro do requirements) ou código quebrado.
- AVISO = arquivo diferente do pacote entregue (normal se VOCÊ mexeu nele de propósito).
Para atualizar a lista de referência depois de alterar algo de propósito:  python verificar_projeto.py --gerar
"""
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
MANIFESTO = RAIZ / "MANIFESTO.json"
IGNORAR = {".git", "__pycache__", ".devcontainer", "bipagem_logs", ".venv", "venv", "node_modules"}
EXTENSOES = {".py", ".md", ".txt", ".sql", ".yml", ".yaml", ".toml", ".bat", ".exemplo", ".html"}

# arquivo -> (tamanho mínimo em bytes, textos que PRECISAM aparecer nele)
ESSENCIAIS = {
    "app.py": (2000, ["PAGINAS_ADM"]),
    "README.md": (12000, ["# ", "Histórico de mudanças", "Regras que não podem quebrar", "Mapa dos arquivos"]),
    "MELHORIAS.md": (500, ["# "]),
    "requirements.txt": (40, ["streamlit", "supabase"]),
    "requirements-worker.txt": (30, ["supabase", "pandas", "cryptography"]),
    "requirements-agente.txt": (20, ["selenium", "supabase"]),
    ".gitignore": (30, ["secrets"]),
    ".env.exemplo": (100, ["SUPABASE_URL", "USUARIO"]),
    "secrets.exemplo.toml": (300, ["SUPABASE_URL", "EMPRESA_NOME"]),
    "iniciar_agente.bat": (50, ["bipagem.agente"]),
    ".github/workflows/disparador.yml": (800, ["disparador.worker", "workflow_dispatch"]),
    ".github/workflows/verificar.yml": (200, ["verificar_projeto.py"]),
    "migracao.sql": (500, ["create"]),
    "migracao_v2.sql": (300, ["alter", "create"]),
    "migracao_v3.sql": (500, ["create"]),
    "migracao_v4.sql": (1000, ["campanhas"]),
    "migracao_v5.sql": (800, ["bipagem_lotes", "qtd_acrescimo"]),
    "migracao_v6.sql": (1500, ["create index", "limpar_historico_antigo"]),
    ".github/workflows/manter_ativo.yml": (300, ["APP_URL"]),
    "ui/coletor/camera.py": (800, ["camera_leve"]),
    "ui/coletor/camera_leve/index.html": (1500, ["streamlit:componentReady", "setComponentValue"]),
    "bipagem/agente.py": (2000, ["def main"]),
    "bipagem/motor.py": (2000, ["def "]),
    "bipagem/reintegra.py": (2000, ["selenium"]),
    "disparador/worker.py": (3000, ["def processar_campanha"]),
    "disparador/variacoes.py": (2000, ["def atribuir"]),
    "disparador/contato.py": (2000, ["def quem_clicou"]),
    "disparador/ui.py": (10000, ["def renderizar_disparador"]),
    "core/financeiro.py": (3000, ["def calcular_fechamento"]),
}
LINHA_REQUIREMENTS = re.compile(r"^[A-Za-z0-9_.\-\[\]]+\s*([<>=!~]=?[^#\s]+(\s*,\s*[<>=!~]=?[^#\s]+)*)?\s*(#.*)?$")


def arquivos():
    for p in sorted(RAIZ.rglob("*")):
        if p.is_file() and not (set(p.relative_to(RAIZ).parts) & IGNORAR) and (p.suffix in EXTENSOES or p.name.startswith(".")):
            yield p


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verificar():
    erros, avisos = [], []
    for p in arquivos():
        rel = p.relative_to(RAIZ).as_posix()
        dados = p.read_bytes()
        if rel == "MANIFESTO.json":
            continue
        if not dados.strip():
            erros.append(f"VAZIO: {rel}")
            continue
        texto = dados.decode("utf-8", errors="replace")
        if p.suffix == ".py":
            try:
                ast.parse(texto)
            except SyntaxError as e:
                erros.append(f"CÓDIGO QUEBRADO: {rel} (linha {e.lineno}: {e.msg})")
        if p.name.startswith("requirements") and p.suffix == ".txt":
            for n, linha in enumerate(texto.splitlines(), 1):
                if linha.strip() and not linha.lstrip().startswith("#") and not LINHA_REQUIREMENTS.match(linha.strip()):
                    erros.append(f"CONTEÚDO TROCADO: {rel} (linha {n} não é um pacote: {linha.strip()[:50]!r})")
                    break
        if p.suffix == ".md" and texto.lstrip().lower().startswith("@echo"):
            erros.append(f"CONTEÚDO TROCADO: {rel} tem texto de um arquivo .bat")
        if p.suffix == ".bat" and texto.lstrip().startswith("#"):
            erros.append(f"CONTEÚDO TROCADO: {rel} tem texto de um arquivo de documentação")
    for rel, (minimo, termos) in ESSENCIAIS.items():
        p = RAIZ / rel
        if not p.exists():
            erros.append(f"FALTANDO: {rel}")
            continue
        dados = p.read_bytes()
        if dados.strip() and len(dados) < minimo:
            erros.append(f"INCOMPLETO: {rel} tem só {len(dados)} bytes (o esperado é pelo menos {minimo})")
        texto = dados.decode("utf-8", errors="replace").lower()
        faltam = [t for t in termos if t.lower() not in texto]
        if dados.strip() and faltam:
            erros.append(f"CONTEÚDO ESTRANHO: {rel} não contém {faltam} (arquivo trocado?)")
    if (RAIZ / "modulo_email.py").exists():
        avisos.append("modulo_email.py é a versão ANTIGA do disparador e não é mais usado: pode apagar.")
    if MANIFESTO.exists():
        ref = json.loads(MANIFESTO.read_text(encoding="utf-8"))
        atuais = {p.relative_to(RAIZ).as_posix(): p for p in arquivos() if p.name != "MANIFESTO.json"}
        for rel, info in ref.items():
            p = atuais.get(rel)
            if p is None:
                avisos.append(f"não está no seu projeto (veio no pacote): {rel}")
            elif p.stat().st_size != info["bytes"] or sha(p) != info["sha256"]:
                avisos.append(f"diferente do pacote entregue: {rel} ({p.stat().st_size} bytes; esperado {info['bytes']})")
    return erros, avisos


def gerar():
    ref = {p.relative_to(RAIZ).as_posix(): {"bytes": p.stat().st_size, "sha256": sha(p)}
           for p in arquivos() if p.name != "MANIFESTO.json" and p.stat().st_size > 0}
    MANIFESTO.write_text(json.dumps(ref, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"MANIFESTO.json gerado com {len(ref)} arquivos.")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--gerar" in argv:
        gerar()
        return 0
    erros, avisos = verificar()
    for a in avisos:
        print("AVISO ", a)
    for e in erros:
        print("ERRO  ", e)
    total = sum(1 for _ in arquivos())
    if erros:
        print(f"\n❌ {len(erros)} problema(s) em {total} arquivos. Suba de novo os arquivos acima usando 'Upload files' "
              "(não copie e cole o texto).")
        return 1
    print(f"✅ {total} arquivos conferidos: nenhum vazio, nenhum trocado." + (f" ({len(avisos)} aviso(s))" if avisos else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
