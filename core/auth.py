"""Autenticação: senhas com bcrypt, token de sessão com hash e limite de tentativas."""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

import bcrypt

from .resiliencia import com_tentativas

MIN_SENHA = 8  # só vale para senhas NOVAS; quem já tem senha de 6 continua entrando e é orientado a trocar
MAX_BYTES_SENHA = 72  # limite do bcrypt


def _bytes(senha):
    return str(senha).encode("utf-8")[:MAX_BYTES_SENHA]


def gerar_hash_senha(senha):
    return bcrypt.hashpw(_bytes(senha), bcrypt.gensalt()).decode("utf-8")


def conferir_senha(digitada, salva):
    """Devolve (ok, precisa_migrar). Senhas antigas em texto puro são aceitas uma vez e trocadas por hash."""
    salva = str(salva or "")
    if salva.startswith("$2"):
        try:
            return bcrypt.checkpw(_bytes(digitada), salva.encode("utf-8")), False
        except (ValueError, TypeError):
            return False, False
    ok = hmac.compare_digest(str(digitada).encode("utf-8"), salva.encode("utf-8"))
    return ok, ok


def hash_token(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def validar_senha_nova(senha):
    """Devolve texto do problema ou None se estiver ok."""
    if len(senha or "") < MIN_SENHA:
        return f"A senha precisa ter pelo menos {MIN_SENHA} caracteres."
    if not str(senha).strip():
        return "A senha não pode ser só espaços."
    if len(str(senha).encode("utf-8")) > MAX_BYTES_SENHA:
        return f"A senha é longa demais (máximo {MAX_BYTES_SENHA} bytes)."
    return None


class Limitador:
    """Bloqueia por um tempo quem erra a senha várias vezes seguidas."""

    def __init__(self, max_falhas=5, janela_seg=300, relogio=time.time):
        self.max_falhas, self.janela, self.relogio = max_falhas, janela_seg, relogio
        self._falhas = {}

    def _recentes(self, chave):
        agora = self.relogio()
        lista = [t for t in self._falhas.get(chave, []) if agora - t < self.janela]
        if lista:
            self._falhas[chave] = lista
        else:
            self._falhas.pop(chave, None)
        return lista

    def bloqueado(self, chave):
        return len(self._recentes(chave)) >= self.max_falhas

    def registrar_falha(self, chave):
        self._falhas.setdefault(chave, []).append(self.relogio())

    def limpar(self, chave):
        self._falhas.pop(chave, None)

    def segundos_restantes(self, chave):
        lista = self._recentes(chave)
        if len(lista) < self.max_falhas:
            return 0
        return max(0, int(self.janela - (self.relogio() - min(lista))))


@dataclass
class ResultadoLogin:
    ok: bool
    usuario: dict = field(default_factory=dict)
    token: str = ""
    mensagem: str = ""


def dados_publicos(linha):
    return {k: linha.get(k) for k in ("id", "usuario", "nome_completo", "cargo", "trocar_senha")}


def autenticar(sb, usuario, senha, limitador):
    usuario = (usuario or "").strip().lower()
    if not usuario or not senha:
        return ResultadoLogin(False, mensagem="Informe usuário e senha.")
    if limitador.bloqueado(usuario):
        minutos = max(1, limitador.segundos_restantes(usuario) // 60 + 1)
        return ResultadoLogin(False, mensagem=f"Muitas tentativas incorretas. Aguarde cerca de {minutos} min.")

    res = com_tentativas(sb.table("usuarios").select("*").eq("usuario", usuario).limit(1).execute)
    linha = res.data[0] if res.data else None
    ok, migrar = conferir_senha(senha, linha["senha"]) if linha else (False, False)
    if not (linha and ok):
        limitador.registrar_falha(usuario)
        return ResultadoLogin(False, mensagem="Usuário ou senha incorretos.")
    if linha.get("ativo") is False:
        return ResultadoLogin(False, mensagem="Usuário desativado. Fale com o administrador.")

    token = secrets.token_urlsafe(32)
    mudancas = {"session_token": hash_token(token)}
    if migrar:
        mudancas["senha"] = gerar_hash_senha(senha)
    sb.table("usuarios").update(mudancas).eq("id", linha["id"]).execute()
    limitador.limpar(usuario)
    return ResultadoLogin(True, usuario=dados_publicos(linha), token=token)


def usuario_por_token(sb, token):
    """Recupera o usuário a partir do cookie de sessão (None se inválido ou desativado)."""
    if not token:
        return None
    res = com_tentativas(sb.table("usuarios").select("*").eq("session_token", hash_token(token)).limit(1).execute)
    if not res.data or res.data[0].get("ativo") is False:
        return None
    return dados_publicos(res.data[0])


def encerrar_sessao(sb, usuario_id):
    sb.table("usuarios").update({"session_token": None}).eq("id", usuario_id).execute()


def definir_senha(sb, usuario_id, nova_senha, encerrar_sessoes=True, exigir_troca=False):
    """Grava a senha (hash). `exigir_troca=True` (senha definida pelo administrador): no próximo acesso o usuário é obrigado a criar a dele."""
    mudancas = {"senha": gerar_hash_senha(nova_senha)}
    if encerrar_sessoes:
        mudancas["session_token"] = None
    if exigir_troca:
        mudancas["trocar_senha"] = True
    sb.table("usuarios").update(mudancas).eq("id", usuario_id).execute()


def alterar_propria_senha(sb, usuario_id, senha_atual, nova_senha):
    """Devolve (ok, mensagem)."""
    problema = validar_senha_nova(nova_senha)
    if problema:
        return False, problema
    res = sb.table("usuarios").select("senha").eq("id", usuario_id).limit(1).execute()
    if not res.data:
        return False, "Usuário não encontrado."
    ok, _ = conferir_senha(senha_atual, res.data[0]["senha"])
    if not ok:
        return False, "A senha atual está incorreta."
    definir_senha(sb, usuario_id, nova_senha, encerrar_sessoes=False)
    return True, "Senha alterada."


# ------------------------------------------------------------------ esqueci a senha (pedido ao administrador)
ALFABETO_TEMPORARIA = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # sem 0/O, 1/l/I (confundem na leitura)
MAX_PEDIDOS_ABERTOS = 50  # trava contra enchente de pedidos falsos
MENSAGEM_PEDIDO = ("Pedido enviado. Se esse usuário existir, o administrador vai gerar uma senha temporária e avisar você. "
                   "No primeiro acesso, você cria a sua senha.")


def gerar_senha_temporaria(tamanho=10):
    return "".join(secrets.choice(ALFABETO_TEMPORARIA) for _ in range(tamanho))


def pedir_redefinicao(sb, usuario):
    """Registra o pedido de nova senha. A resposta ao usuário é sempre a mesma (não revela se o login existe)."""
    usuario = (usuario or "").strip().lower()
    if not usuario or len(usuario) > 60:
        return
    linha = sb.table("usuarios").select("id,ativo").eq("usuario", usuario).limit(1).execute().data
    if not linha or linha[0].get("ativo") is False:
        return
    abertos = sb.table("pedidos_senha").select("id,usuario").eq("atendido", False).limit(MAX_PEDIDOS_ABERTOS + 1).execute().data or []
    if len(abertos) > MAX_PEDIDOS_ABERTOS or any(a["usuario"] == usuario for a in abertos):
        return
    sb.table("pedidos_senha").insert({"usuario": usuario, "atendido": False}).execute()


def pedidos_abertos(sb):
    """Pedidos ainda não atendidos, com o nome da pessoa (mais antigos primeiro)."""
    pedidos = sb.table("pedidos_senha").select("id,usuario,criado_em").eq("atendido", False).order("criado_em").limit(100).execute().data or []
    if not pedidos:
        return []
    nomes = {u["usuario"]: u["nome_completo"] for u in
             sb.table("usuarios").select("usuario,nome_completo").in_("usuario", [p["usuario"] for p in pedidos]).execute().data or []}
    return [{**p, "nome_completo": nomes.get(p["usuario"], p["usuario"])} for p in pedidos]


def atender_pedido(sb, pedido, quem):
    """Gera a senha temporária, derruba as sessões do usuário, exige a troca no próximo acesso e fecha o pedido. Devolve a senha."""
    alvo = sb.table("usuarios").select("id").eq("usuario", pedido["usuario"]).limit(1).execute().data
    if not alvo:
        raise ValueError("Usuário não existe mais.")
    temporaria = gerar_senha_temporaria()
    definir_senha(sb, alvo[0]["id"], temporaria, encerrar_sessoes=True, exigir_troca=True)
    sb.table("pedidos_senha").update({"atendido": True, "atendido_por": quem}).eq("usuario", pedido["usuario"]).eq("atendido", False).execute()
    return temporaria


def ignorar_pedido(sb, pedido, quem):
    sb.table("pedidos_senha").update({"atendido": True, "atendido_por": f"{quem} (ignorado)"}).eq("usuario", pedido["usuario"]).eq("atendido", False).execute()


def concluir_troca_obrigatoria(sb, usuario_id, nova_senha):
    """Primeiro acesso com senha temporária/definida pelo administrador. Devolve (ok, mensagem)."""
    problema = validar_senha_nova(nova_senha)
    if problema:
        return False, problema
    atual = sb.table("usuarios").select("senha").eq("id", usuario_id).limit(1).execute().data
    if not atual:
        return False, "Usuário não encontrado."
    if conferir_senha(nova_senha, atual[0]["senha"])[0]:
        return False, "Escolha uma senha diferente da temporária."
    sb.table("usuarios").update({"senha": gerar_hash_senha(nova_senha), "trocar_senha": False}).eq("id", usuario_id).execute()
    return True, "Senha criada."
