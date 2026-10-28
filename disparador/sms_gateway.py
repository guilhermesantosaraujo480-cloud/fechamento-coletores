"""Cliente do app "SMS Gateway for Android" (SMSGate, sms-gate.app): o celular com o chip envia o SMS.

Como funciona: o app no celular fica ligado e com internet (modo **Cloud Server**); esta plataforma manda o pedido para a API
da nuvem do app (`https://api.sms-gate.app`) e o celular envia pelo chip. No app aparecem o **usuário** e a **senha** da API:
é isso que se cadastra em 📱 SMS → Celulares.

API usada (docs.sms-gate.app):
    POST {base}/3rdparty/v1/messages   corpo: {"textMessage": {"text": ...}, "phoneNumbers": ["+55..."], "simNumber": 1, "ttl": 7200}
         (versões antigas usam /3rdparty/v1/message: tentamos esse caminho se o primeiro responder 404)
    resposta 202: {"id": "...", "state": "Pending", ...}
    GET  {base}/3rdparty/v1/messages/{id}   estado: Pending | Processed | Sent | Delivered | Failed
    GET  {base}/3rdparty/v1/devices          celulares ligados à conta (usado no "Testar conexão")
Autenticação: HTTP Basic (usuário:senha do app). O app tem ritmo, limite por hora/dia e horário próprios (Configurações → Mensagens).
Privacidade: o texto e o número passam pelo servidor do app (HTTPS). O app oferece criptografia de ponta a ponta e servidor privado.
Só biblioteca padrão. `abrir` pode ser trocado nos testes.
"""
import base64
import json
import urllib.error
import urllib.request

URL_NUVEM = "https://api.sms-gate.app"
CAMINHOS = ("/3rdparty/v1/messages", "/3rdparty/v1/message")
CAMINHO_DISPOSITIVOS = "/3rdparty/v1/devices"
TEMPO_LIMITE = 25
TTL_PADRAO = 7200  # se o celular ficar desligado, o pedido vence em 2 h em vez de sair atrasado


class ErroGateway(RuntimeError):
    """tipo: 'credencial' (usuário/senha/permissão: o celular inteiro não serve), 'numero' (este SMS foi recusado),
    'temporario' (sem rede, limite, servidor fora: tentar de novo depois). `espera` = segundos sugeridos."""

    def __init__(self, mensagem, tipo="temporario", espera=0):
        super().__init__(mensagem)
        self.tipo, self.espera = tipo, espera

    @property
    def definitivo(self):
        return self.tipo != "temporario"


def _abrir_padrao(req, timeout):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — URL vem do cadastro do administrador
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _json(corpo):
    try:
        return json.loads(corpo.decode("utf-8")) if corpo else {}
    except (ValueError, UnicodeDecodeError):
        return {}


class Gateway:
    def __init__(self, url_base, usuario, senha, sim=None, abrir=None):
        self.base = (url_base or URL_NUVEM).strip().rstrip("/")
        if not self.base.startswith(("http://", "https://")):
            self.base = "https://" + self.base
        self.usuario, self._senha, self.sim = str(usuario or ""), str(senha or ""), sim
        self._abrir = abrir or _abrir_padrao

    def _pedido(self, metodo, caminho, corpo=None):
        credencial = base64.b64encode(f"{self.usuario}:{self._senha}".encode()).decode()
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(self.base + caminho, data=dados, method=metodo, headers={
            "Authorization": f"Basic {credencial}", "Content-Type": "application/json", "Accept": "application/json"})
        try:
            status, resp = self._abrir(req, TEMPO_LIMITE)
        except (urllib.error.URLError, TimeoutError, OSError) as erro:
            raise ErroGateway(f"Sem conexão com o servidor do aplicativo: {erro}") from erro
        return status, _json(resp)

    def enviar(self, telefone, texto, ttl=TTL_PADRAO):
        """Entrega o SMS ao app. Devolve (id_da_mensagem, estado). O app envia pelo chip no ritmo dele."""
        corpo = {"textMessage": {"text": texto}, "phoneNumbers": [telefone], "ttl": int(ttl)}
        if self.sim:
            corpo["simNumber"] = int(self.sim)
        status, r = 404, {}
        for caminho in CAMINHOS:
            status, r = self._pedido("POST", caminho, corpo)
            if status != 404:
                break
        if status in (200, 201, 202):
            return str(r.get("id") or ""), str(r.get("state") or r.get("status") or "Pending")
        detalhe = str(r.get("message") or r.get("error") or "")[:150]
        if status == 401:
            raise ErroGateway("Usuário ou senha do aplicativo incorretos (veja a tela do app, em Cloud Server).", "credencial")
        if status == 403:
            raise ErroGateway("Sem permissão para enviar (confira usuário/senha e se o app está no modo Cloud Server).", "credencial")
        if status == 404:
            raise ErroGateway("Endereço da API não encontrado (confira a URL do servidor).", "credencial")
        if status in (400, 422):
            raise ErroGateway(f"O aplicativo recusou o pedido: {detalhe or status}", "numero")
        if status == 429:
            raise ErroGateway("Limite de envio do aplicativo atingido; tentamos de novo depois.", "temporario", int(r.get("retryAfter") or 60))
        if status == 503:
            raise ErroGateway(f"Fila do aplicativo cheia ou sem celular conectado ({detalhe or 'QueueLimitExceeded'}).", "temporario", 120)
        raise ErroGateway(f"O servidor do aplicativo respondeu {status}. {detalhe}".strip())

    def consultar(self, id_mensagem):
        """Estado da mensagem ('Pending', 'Sent', 'Delivered', 'Failed'...) ou '' se o servidor não informar."""
        if not id_mensagem:
            return ""
        try:
            status, r = self._pedido("GET", f"{CAMINHOS[0]}/{id_mensagem}")
        except ErroGateway:
            return ""
        return str(r.get("state") or r.get("status") or "") if status == 200 else ""

    def testar(self):
        """(ok, texto) — confere usuário/senha e mostra quantos celulares estão ligados à conta."""
        try:
            status, r = self._pedido("GET", CAMINHO_DISPOSITIVOS)
        except ErroGateway as erro:
            return False, str(erro)
        if status in (401, 403):
            return False, "Usuário ou senha incorretos."
        if status != 200:
            return False, f"O servidor respondeu {status}."
        aparelhos = r if isinstance(r, list) else (r.get("devices") or r.get("items") or [])
        if not aparelhos:
            return True, "Conectou, mas nenhum celular aparece. Abra o app, ligue o Cloud Server e toque em Online."
        nomes = ", ".join(str(a.get("name") or a.get("id") or "celular") for a in aparelhos if isinstance(a, dict)) or f"{len(aparelhos)}"
        return True, f"Conectado. Celular(es): {nomes}."


def criar(linha, cofre, abrir=None):
    """Gateway a partir de uma linha da tabela sms_gateways (senha protegida pelo cofre). None se a senha for ilegível."""
    senha = cofre.revelar(linha.get("senha"))
    if not senha:
        return None
    return Gateway(linha.get("url_base") or URL_NUVEM, linha.get("usuario"), senha, linha.get("sim_numero"), abrir)
