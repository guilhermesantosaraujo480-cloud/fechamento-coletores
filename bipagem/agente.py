"""Agente local da bipagem. Deixe rodando no seu computador:  python -m bipagem.agente

Ele fica olhando a fila do site; quando você coloca um lote lá, abre o Chrome, entra na Reintegra com o
SEU usuário/senha (do arquivo .env, que nunca sai do computador) e bipa. Pode parar pelo site.
Requer .env com SUPABASE_URL, SUPABASE_KEY, USUARIO e SENHA (os mesmos nomes do script antigo)."""
import csv
import os
import socket
import sys
import time

from . import fila, motor


class ApiLote:
    """Liga o motor ao banco. Falha de rede NÃO derruba o lote: registra e segue (o Wi-Fi pode oscilar no meio)."""

    def __init__(self, sb, lote_id, pasta_logs="bipagem_logs", log=print):
        self.sb, self.id, self.log = sb, lote_id, log
        os.makedirs(pasta_logs, exist_ok=True)
        self.csv = os.path.join(pasta_logs, f"lote_{lote_id}.csv")

    def _seguro(self, f, *a, padrao=None, **k):
        try:
            return f(self.sb, *a, **k)
        except Exception as erro:  # noqa: BLE001
            self.log(f"   (aviso: não consegui falar com o banco agora: {erro})")
            return padrao

    def deve_parar(self):
        return bool(self._seguro(fila.deve_parar, self.id, padrao=False))

    def progresso(self, **campos):
        self._seguro(fila.progresso, self.id, **campos)

    def sinal(self, info=""):
        self._seguro(fila.sinal, info=info)

    def item(self, os, status, serial1="", serial2="", tentativas=0, obs=""):
        novo = not os_path_exists(self.csv)
        with open(self.csv, "a", newline="", encoding="utf-8-sig") as f:  # backup local, mesmo sem internet
            w = csv.writer(f, delimiter=";")
            if novo:
                w.writerow(["hora", "os", "status", "serial1", "serial2", "tentativas", "obs"])
            w.writerow([time.strftime("%d/%m/%Y %H:%M:%S"), os, status, serial1, serial2, tentativas, obs])
        self._seguro(fila.registrar_item, self.id, os, status, serial1=serial1, serial2=serial2,
                     tentativas=tentativas, obs=obs)


def os_path_exists(caminho):
    return os.path.exists(caminho)


def _carregar_env():
    try:
        import dotenv
        dotenv.load_dotenv()
    except ImportError:
        pass


def _faltando(env):
    return [k for k in ("SUPABASE_URL", "SUPABASE_KEY", "USUARIO", "SENHA") if not (env.get(k) or "").strip()]


def rodar_lote(sb, lote, env, criar_plataforma, log=print):
    """Executa um lote e grava o desfecho. Devolve o status final."""
    nome = socket.gethostname()
    fila.iniciar(sb, lote, nome)
    log(f"\n=== Lote #{lote['id']} · {lote['nome']} · {lote['limite_ordens']} ordens · {lote['qtd_aparelhos']} aparelho(s)/OS ===")
    api = ApiLote(sb, lote["id"], log=log)
    plataforma = None
    try:
        plataforma = criar_plataforma(env)
        plataforma.entrar()
        status, msg = motor.executar(lote, plataforma, api, log=log)
    except KeyboardInterrupt:
        fila.finalizar(sb, lote["id"], "parado", "Agente interrompido no computador. Clique em Retomar para continuar.")
        raise
    except Exception as erro:  # noqa: BLE001
        status, msg = "erro", f"{type(erro).__name__}: {erro}"[:300]
        log(f"✖ {msg}")
    finally:
        if plataforma is not None:
            plataforma.fechar()
    fila.finalizar(sb, lote["id"], status, msg)
    log(f"=== Lote #{lote['id']} terminou: {status} — {msg}")
    return status


def _criar_plataforma(env):
    from .reintegra import PlataformaReintegra
    return PlataformaReintegra(env["USUARIO"], env["SENHA"], pausa=float(env.get("BIPAGEM_PAUSA") or 1.0),
                               headless=str(env.get("BIPAGEM_HEADLESS", "")).lower() in ("1", "true", "sim"))


def main(env=None, criar_cliente=None, criar_plataforma=_criar_plataforma, dormir=time.sleep, uma_vez=False, log=print):
    _carregar_env()
    env = env if env is not None else os.environ
    falta = _faltando(env)
    if falta:
        log("Faltam no arquivo .env: " + ", ".join(falta))
        return 2
    if criar_cliente is None:
        from supabase import create_client
        criar_cliente = create_client
    sb = criar_cliente(env["SUPABASE_URL"].strip(), env["SUPABASE_KEY"].strip())
    log("Agente da bipagem ligado. Deixe esta janela aberta; para desligar, feche-a ou aperte Ctrl+C.")
    try:
        while True:
            try:
                fila.sinal(sb, info="aguardando lote")
                lote = fila.proximo_lote(sb)
            except Exception as erro:  # noqa: BLE001 — sem internet: espera e tenta de novo
                log(f"(sem conexão com o banco: {erro}) tentando de novo...")
                dormir(15)
                continue
            if lote:
                rodar_lote(sb, lote, env, criar_plataforma, log=log)
            elif uma_vez:
                return 0
            else:
                dormir(10)
            if uma_vez:
                return 0
    except KeyboardInterrupt:
        log("Agente desligado.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
