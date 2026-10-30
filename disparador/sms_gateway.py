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
Autenticação: HTTP Basic (usuário:senha do app). Se o servidor recusar o Basic (401/403), tentamos o login moderno do app: troca usuário/senha
por um token JWT (POST /3rdparty/v1/auth/token) e repete o pedido com "Bearer". Se o token também for recusado, o erro mostra o código HTTP e a
mensagem do servidor, para saber se é mesmo usuário/senha. O app tem ritmo, limite por hora/dia e horário próprios (Configurações → Mensagens).
Privacidade: o texto e o número passam pelo servidor do app (HTTPS). O app oferece criptografia de ponta a ponta e servidor privado.
Só biblioteca padrão. `abrir` pode ser trocado nos testes.
"""
import base64
import json
import unicodedata
import urllib.error
import urllib.request

URL_NUVEM = "https://api.sms-gate.app"
CAMINHOS = ("/3rdparty/v1/messages", "/3rdparty/v1/message")
CAMINHO_DISPOSITIVOS = "/3rdparty/v1/devices"
CAMINHO_TOKEN = "/3rdparty/v1/auth/token"
ESCOPOS_TOKEN = ["messages:send", "messages:read", "messages:list", "devices:list"]
USER_AGENT = "SistemaColetas/1.0 (+envio de SMS)"
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


def limpar_credencial(valor):
    """Tira espaços, quebras de linha e caracteres invisíveis (comuns ao copiar texto de um celular). Usuário e senha do app só têm letras e números."""
    return "".join(c for c in str(valor or "") if c.isprintable() and not c.isspace() and unicodedata.category(c) not in ("Cf", "Zs"))


def limpar_endereco(url):
    """Aceita o endereço do jeito que for colado ('api.sms-gate.app:443', '.../mobile/v1'...) e devolve só 'https://servidor'."""
    base = str(url or "").strip().rstrip("/") or URL_NUVEM
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    for sufixo in ("/mobile/v1", "/3rdparty/v1", "/api/3rdparty/v1", "/api"):
        if base.lower().endswith(sufixo):
            base = base[: -len(sufixo)].rstrip("/")
    if base.startswith("https://") and base.endswith(":443"):
        base = base[: -len(":443")]
    return base


class Gateway:
    def __init__(self, url_base, usuario, senha, sim=None, abrir=None):
        self.base = limpar_endereco(url_base)
        self.usuario, self._senha, self.sim = limpar_credencial(usuario), limpar_credencial(senha), sim
        self._abrir = abrir or _abrir_padrao
        self._token, self._token_recusado, self.ultimo, self.bruto = None, False, (0, ""), ""

    def _pedido(self, metodo, caminho, corpo=None, so_basico=False):
        """(status, json). Usa Bearer se já temos token; no 401/403 tenta trocar usuário/senha por token e repete uma vez."""
        status, resp = self._chamar(metodo, caminho, corpo, so_basico)
        if status in (401, 403) and not so_basico and not self._token and not self._token_recusado:
            if self._obter_token():
                status, resp = self._chamar(metodo, caminho, corpo, False)
        self.ultimo = (status, str(resp.get("message") or resp.get("error") or "")[:150] if isinstance(resp, dict) else "")
        return status, resp

    def _chamar(self, metodo, caminho, corpo, so_basico):
        if self._token and not so_basico:
            autorizacao = f"Bearer {self._token}"
        else:
            autorizacao = "Basic " + base64.b64encode(f"{self.usuario}:{self._senha}".encode()).decode()
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(self.base + caminho, data=dados, method=metodo, headers={
            "Authorization": autorizacao, "Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": USER_AGENT})  # sem isto o urllib se identifica como "Python-urllib" e firewalls (Cloudflare) respondem 403
        try:
            status, resp = self._abrir(req, TEMPO_LIMITE)
        except (urllib.error.URLError, TimeoutError, OSError) as erro:
            raise ErroGateway(f"Sem conexão com o servidor do aplicativo: {erro}") from erro
        self.bruto = "" if _json(resp) else " ".join(resp.decode("utf-8", "replace").split())[:120]
        return status, _json(resp)

    def _obter_token(self):
        """Login moderno: usuário/senha -> token. True se conseguiu (e passa a usar Bearer)."""
        try:
            status, r = self._chamar("POST", CAMINHO_TOKEN, {"ttl": 3600, "scopes": ESCOPOS_TOKEN}, True)
        except ErroGateway:
            self._token_recusado = True
            return False
        token = r.get("access_token") or r.get("accessToken") if isinstance(r, dict) else None
        if status in (200, 201) and token:
            self._token = str(token)
            return True
        self._token_recusado = True
        return False

    def _detalhe(self):
        status, msg = self.ultimo
        msg = msg or (f"resposta: {self.bruto}" if self.bruto else "")
        return f"HTTP {status}" + (f": {msg}" if msg else "")

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
            raise ErroGateway(f"Usuário ou senha do aplicativo incorretos (veja a tela do app, em Cloud Server). [{self._detalhe()}]", "credencial")
        if status == 403:
            raise ErroGateway(f"Sem permissão para enviar (confira usuário/senha e se o app está no modo Cloud Server). [{self._detalhe()}]", "credencial")
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
        """(ok, texto) — confere usuário/senha e mostra quantos celulares estão ligados à conta. O texto traz o código HTTP."""
        try:
            status, r = self._pedido("GET", CAMINHO_DISPOSITIVOS)
        except ErroGateway as erro:
            return False, str(erro)
        if status == 403:  # login reconhecido, mas esta credencial não pode LISTAR celulares (enviar costuma funcionar): confirmar com SMS de teste
            return True, (f"O servidor do app aceitou o login, mas não permite listar os celulares ({self._detalhe()}). Isso é comum e não "
                          "impede o envio: confirme mandando o **SMS de teste** para o seu número na aba ✉️ Enviar.")
        if status == 401:
            return False, (f"Usuário ou senha recusados pelo servidor do app ({self._detalhe()}). Use o Username e a Password do bloco "
                           f"**Cloud server** do app (serviço iniciado) e deixe o endereço exatamente como {URL_NUVEM}.")
        if status == 404:
            return False, f"Endereço da API não encontrado (HTTP 404). Confira se está exatamente {URL_NUVEM}."
        if status != 200:
            return False, f"O servidor respondeu {self._detalhe()}."
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
