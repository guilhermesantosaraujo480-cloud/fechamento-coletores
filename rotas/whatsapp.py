"""Envio pelo WhatsApp através de um 'gateway' (Evolution API ou Z-API).

IMPORTANTE: o WhatsApp oficial não permite mandar para grupos automaticamente. Estes gateways usam um número
conectado por QR code (como o WhatsApp Web) e são NÃO oficiais: há risco de bloqueio do número.
Use um número dedicado à operação, não o pessoal.
"""
import base64

import requests

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ErroWhats(RuntimeError):
    """Mensagem pronta para mostrar ao usuário."""


class Gateway:
    nome = "gateway"

    def __init__(self, http=requests, timeout=60):
        self.http, self.timeout = http, timeout

    def _chamar(self, metodo, url, **kw):
        try:
            r = getattr(self.http, metodo)(url, headers=self._cabecalhos(), timeout=self.timeout, **kw)
        except requests.RequestException as erro:
            raise ErroWhats(f"Sem conexão com o gateway: {erro}") from erro
        if r.status_code >= 400:
            try:
                corpo = str(r.json())[:200]
            except Exception:
                corpo = (getattr(r, "text", "") or "")[:200]
            raise ErroWhats(f"{self.nome} respondeu {r.status_code}: {corpo}")
        try:
            return r.json()
        except Exception:
            return {}

    def _cabecalhos(self):
        return {"Content-Type": "application/json"}


class Evolution(Gateway):
    nome = "Evolution API"

    def __init__(self, url, instancia, apikey, **kw):
        super().__init__(**kw)
        self.url, self.instancia, self.apikey = url.rstrip("/"), instancia, apikey

    def _cabecalhos(self):
        return {"Content-Type": "application/json", "apikey": self.apikey}

    def enviar_texto(self, destino, texto):
        return self._chamar("post", f"{self.url}/message/sendText/{self.instancia}",
                            json={"number": destino, "text": texto})

    def enviar_arquivo(self, destino, conteudo, nome_arquivo, legenda=""):
        return self._chamar("post", f"{self.url}/message/sendMedia/{self.instancia}", json={
            "number": destino, "mediatype": "document", "mimetype": MIME_XLSX, "caption": legenda,
            "fileName": nome_arquivo, "media": base64.b64encode(conteudo).decode()})

    def listar_grupos(self):
        dados = self._chamar("get", f"{self.url}/group/fetchAllGroups/{self.instancia}",
                             params={"getParticipants": "false"})
        return [{"nome": g.get("subject", ""), "destino": g.get("id", "")} for g in (dados if isinstance(dados, list) else [])]


class ZApi(Gateway):
    nome = "Z-API"

    def __init__(self, url, client_token="", **kw):
        super().__init__(**kw)
        self.url, self.client_token = url.rstrip("/"), client_token  # url já inclui /instances/ID/token/TOKEN

    def _cabecalhos(self):
        cab = {"Content-Type": "application/json"}
        if self.client_token:
            cab["Client-Token"] = self.client_token
        return cab

    def enviar_texto(self, destino, texto):
        return self._chamar("post", f"{self.url}/send-text", json={"phone": destino, "message": texto})

    def enviar_arquivo(self, destino, conteudo, nome_arquivo, legenda=""):
        b64 = f"data:{MIME_XLSX};base64," + base64.b64encode(conteudo).decode()
        return self._chamar("post", f"{self.url}/send-document/xlsx",
                            json={"phone": destino, "document": b64, "fileName": nome_arquivo, "caption": legenda})

    def listar_grupos(self):
        dados = self._chamar("get", f"{self.url}/groups", params={"page": 1, "pageSize": 100})
        return [{"nome": g.get("name", ""), "destino": g.get("phone", "")} for g in (dados if isinstance(dados, list) else [])]


def criar_gateway(cfg, http=requests):
    """Lê os secrets (WHATS_PROVEDOR = evolution | zapi). Sem configuração devolve None (modo manual)."""
    provedor = str(cfg("WHATS_PROVEDOR", "")).strip().lower()
    url = str(cfg("WHATS_API_URL", "")).strip()
    if provedor == "evolution" and url and cfg("WHATS_API_KEY", "") and cfg("WHATS_INSTANCIA", ""):
        return Evolution(url, str(cfg("WHATS_INSTANCIA")), str(cfg("WHATS_API_KEY")), http=http)
    if provedor == "zapi" and url:
        return ZApi(url, str(cfg("WHATS_CLIENT_TOKEN", "")), http=http)
    return None
