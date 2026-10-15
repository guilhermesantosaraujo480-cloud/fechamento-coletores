"""Acorda o trabalhador do GitHub Actions na hora (sem esperar o agendamento). Opcional: sem isso a fila anda no próximo ciclo."""
import requests

WORKFLOW_PADRAO = "disparador.yml"


class ErroGatilho(RuntimeError):
    pass


def configurado(cfg):
    return bool(str(cfg("GITHUB_REPO", "")).strip() and str(cfg("GITHUB_TOKEN_DISPARO", "")).strip())


def disparar_workflow(repo, token, workflow=WORKFLOW_PADRAO, ref="main", http=requests, timeout=20):
    """POST /repos/{repo}/actions/workflows/{workflow}/dispatches. Sucesso = HTTP 204."""
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
    cab = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28"}
    try:
        r = http.post(url, headers=cab, json={"ref": ref}, timeout=timeout)
    except requests.RequestException as erro:
        raise ErroGatilho(f"Sem conexão com o GitHub: {erro}") from erro
    if r.status_code != 204:
        dica = {401: "token inválido ou expirado", 403: "o token não tem permissão de Actions (leitura e escrita)",
                404: "repositório ou arquivo do fluxo não encontrado (confira GITHUB_REPO e o nome do fluxo)",
                422: "o nome do branch (GITHUB_BRANCH) não existe ou o fluxo não tem 'workflow_dispatch'"}.get(r.status_code, "")
        raise ErroGatilho(f"GitHub respondeu {r.status_code}" + (f": {dica}" if dica else ""))


def disparar_pela_tela(cfg, http=requests):
    disparar_workflow(str(cfg("GITHUB_REPO")).strip(), str(cfg("GITHUB_TOKEN_DISPARO")).strip(),
                      str(cfg("GITHUB_WORKFLOW", WORKFLOW_PADRAO)).strip() or WORKFLOW_PADRAO,
                      str(cfg("GITHUB_BRANCH", "main")).strip() or "main", http)
