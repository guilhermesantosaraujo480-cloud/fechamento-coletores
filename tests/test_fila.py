"""Fila de disparo em segundo plano: criação, trabalhador, pausa, limite diário, recuperação de queda, gatilho."""
import unittest

from tests import fakes

fakes.instalar()

from disparador import fila, gatilho, worker  # noqa: E402
from disparador.crypto import Cofre  # noqa: E402


def registros(n=4, repetir_primeiro=False):
    regs = [{"protocolo": f"P{i}", "nome": f"Cliente {i}", "email": f"c{i}@exemplo.com", "endereco": "Rua A",
             "numero": "1", "bairro": "B", "cep": "01000-000", "tipo": "voluntario"} for i in range(n)]
    if repetir_primeiro:
        regs.append(dict(regs[0]))
    return regs


CTX = {"empresa": "Empresa", "identificacao": "CNPJ", "valor_multa": "", "url_clique": "", "num_whatsapp": "5511999999999"}
CONTA = {"id": 1, "email": "c@g.com", "nome_remetente": "E", "limite_diario": 50, "ativa": True, "senha_app": "pura"}


class SMTPFalso:
    def __init__(self, ao_enviar=None, falhar=False):
        self.enviadas, self.ao_enviar, self.falhar = [], ao_enviar, falhar

    def send_message(self, msg):
        if self.falhar:
            raise RuntimeError("falha simulada")
        self.enviadas.append(msg["To"])
        if self.ao_enviar:
            self.ao_enviar(len(self.enviadas))

    def quit(self):
        pass


class Relogio:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


class Base(unittest.TestCase):
    def setUp(self):
        self.sb = fakes.FakeSupabase(contas_email=[dict(CONTA)])
        self.relogio = Relogio()
        self.smtp = SMTPFalso()

    def criar(self, regs=None, **kw):
        regs = regs if regs is not None else registros()
        return fila.criar_campanha(self.sb, "adm", "Teste", "Padrão", {"tipo": "padrao1"}, CTX,
                                   kw.get("dmin", 5), kw.get("dmax", 5), kw.get("reenvio", False), regs)

    def rodar(self, minutos=14, **kw):
        return worker.rodar(self.sb, Cofre(None), minutos, fabrica_smtp=lambda e, s: self.smtp, relogio=self.relogio,
                            dormir=self.relogio.dormir, sortear=lambda a, b: a, log=lambda *a: None)

    def status(self, cid):
        return fila.obter(self.sb, cid)["status"]


class TestFila(Base):
    def test_criar_marca_duplicado_na_planilha(self):
        c = self.criar(registros(3, repetir_primeiro=True))
        ds = fila.destinos(self.sb, c["id"])
        self.assertEqual(len(ds), 4)
        self.assertEqual(sum(d["status"] == "ignorado" for d in ds), 1)
        self.assertEqual(fila.obter(self.sb, c["id"])["ignorados"], 1)

    def test_envia_tudo_e_conclui(self):
        c = self.criar()
        self.rodar()
        self.assertEqual(self.status(c["id"]), "concluida")
        camp = fila.obter(self.sb, c["id"])
        self.assertEqual((camp["enviados"], camp["erros"]), (4, 0))
        self.assertEqual(len(self.smtp.enviadas), 4)
        self.assertEqual(len(self.sb.tabelas["envios_email"]), 4)
        self.assertTrue(all(d["status"] == "enviado" for d in fila.destinos(self.sb, c["id"])))

    def test_tempo_esgotado_continua_no_proximo_ciclo_sem_duplicar(self):
        c = self.criar(registros(10))
        houve, restante = self.rodar(minutos=0.2)  # ~12 s = 2-3 e-mails
        self.assertTrue(restante)
        self.assertEqual(self.status(c["id"]), "pendente")
        primeiros = len(self.smtp.enviadas)
        self.assertTrue(0 < primeiros < 10)
        self.assertEqual(fila.pendentes_na_campanha(self.sb, c["id"]), 10 - primeiros)
        self.rodar()
        self.assertEqual(self.status(c["id"]), "concluida")
        self.assertEqual(len(self.smtp.enviadas), 10)
        self.assertEqual(len(set(self.smtp.enviadas)), 10)

    def test_pausar_na_tela_para_o_envio(self):
        c = self.criar(registros(10))
        self.smtp.ao_enviar = lambda n: fila.pausar(self.sb, c["id"]) if n == 2 else None
        self.rodar()
        self.assertEqual(self.status(c["id"]), "pausada")
        self.assertEqual(len(self.smtp.enviadas), 2)
        self.assertEqual(fila.pendentes_na_campanha(self.sb, c["id"]), 8)
        self.assertIsNone(fila.obter(self.sb, c["id"])["lease_ate"])
        # pausada não anda sozinha; retomar continua
        self.rodar()
        self.assertEqual(len(self.smtp.enviadas), 2)
        fila.retomar(self.sb, c["id"])
        self.rodar()
        self.assertEqual(self.status(c["id"]), "concluida")
        self.assertEqual(len(set(self.smtp.enviadas)), 10)

    def test_cancelar(self):
        c = self.criar(registros(10))
        self.smtp.ao_enviar = lambda n: fila.cancelar(self.sb, c["id"]) if n == 1 else None
        self.rodar()
        self.assertEqual(self.status(c["id"]), "cancelada")
        self.assertEqual(len(self.smtp.enviadas), 1)

    def test_limite_diario_espera_e_retoma(self):
        self.sb.tabelas["contas_email"][0]["limite_diario"] = 2
        c = self.criar(registros(5))
        self.rodar()
        self.assertEqual(self.status(c["id"]), "pendente")
        self.assertIn("Limite diário", fila.obter(self.sb, c["id"])["motivo"])
        self.assertEqual(len(self.smtp.enviadas), 2)
        self.rodar()  # mesmo dia: nada novo
        self.assertEqual(len(self.smtp.enviadas), 2)
        self.sb.tabelas["contas_email"][0]["limite_diario"] = 50  # "dia seguinte"
        self.rodar()
        self.assertEqual(self.status(c["id"]), "concluida")
        self.assertEqual(len(set(self.smtp.enviadas)), 5)

    def test_erros_seguidos_pausam(self):
        self.smtp.falhar = True
        c = self.criar(registros(10))
        self.rodar()
        self.assertEqual(self.status(c["id"]), "pausada")
        self.assertIn("erros seguidos", fila.obter(self.sb, c["id"])["motivo"])
        self.assertEqual(fila.obter(self.sb, c["id"])["erros"], 5)
        self.assertEqual(fila.pendentes_na_campanha(self.sb, c["id"]), 5)
        # corrigido o problema: recolocar os erros e retomar envia tudo
        self.smtp.falhar = False
        self.assertEqual(fila.recolocar_erros(self.sb, c["id"]), 5)
        self.rodar()
        self.assertEqual(self.status(c["id"]), "concluida")
        self.assertEqual(len(self.smtp.enviadas), 10)

    def test_queda_do_trabalhador_nao_duplica(self):
        c = self.criar(registros(3))
        ds = self.sb.tabelas["campanha_destinos"]
        ds[0]["status"] = "enviando"   # saiu, mas o trabalhador caiu antes de anotar
        ds[1]["status"] = "enviando"   # não chegou a sair
        self.sb.tabelas.setdefault("envios_email", []).append({"id": 1, "protocolo": "P0", "email": "c0@exemplo.com", "conta": "c@g.com",
                                                 "status": "enviado", "data_hora": "2026-01-01T00:00:00+00:00"})
        self.rodar()
        self.assertEqual(self.status(c["id"]), "concluida")
        self.assertEqual(sorted(self.smtp.enviadas), ["c1@exemplo.com", "c2@exemplo.com"])
        self.assertEqual(fila.destinos(self.sb, c["id"])[0]["status"], "enviado")

    def test_reserva_impede_dois_trabalhadores(self):
        c = self.criar()
        fila.reservar(self.sb, c, segundos=600)
        self.rodar()
        self.assertEqual(len(self.smtp.enviadas), 0)
        self.assertEqual(self.status(c["id"]), "rodando")

    def test_sem_conta_pausa(self):
        self.sb.tabelas["contas_email"].clear()
        c = self.criar()
        self.rodar()
        self.assertEqual(self.status(c["id"]), "pausada")

    def test_pulados_descadastro_e_ja_enviado(self):
        self.sb.tabelas["descadastros"] = [{"email": "c1@exemplo.com", "motivo": "x", "data_hora": "2026-01-01T00:00:00+00:00"}]
        self.sb.tabelas["envios_email"] = [{"id": 1, "protocolo": "P2", "email": "c2@exemplo.com", "conta": "c@g.com",
                                            "status": "enviado", "data_hora": "2020-01-01T00:00:00+00:00"}]
        c = self.criar()
        self.rodar()
        camp = fila.obter(self.sb, c["id"])
        self.assertEqual((camp["enviados"], camp["ignorados"]), (2, 2))
        self.assertEqual(sorted(self.smtp.enviadas), ["c0@exemplo.com", "c3@exemplo.com"])

    def test_main_sem_configuracao_e_com_configuracao(self):
        self.assertEqual(worker.main(env={}), 1)
        self.criar()
        self.smtp = SMTPFalso()
        chamadas = []
        orig = worker.rodar
        worker.rodar = lambda sb, cofre, minutos: (chamadas.append(minutos), (False, False))[1]
        try:
            self.assertEqual(worker.main(env={"SUPABASE_URL": "u", "SUPABASE_KEY": "k", "MAX_MINUTOS": "3"},
                                         criar_cliente=lambda u, k: self.sb), 0)
        finally:
            worker.rodar = orig
        self.assertEqual(chamadas, [3.0])


class Resp:
    def __init__(self, c):
        self.status_code = c


class TestGatilho(unittest.TestCase):
    def test_sucesso_e_erros(self):
        class Http:
            def __init__(self, codigo):
                self.codigo, self.chamadas = codigo, []

            def post(self, url, **kw):
                self.chamadas.append((url, kw))
                return Resp(self.codigo)
        h = Http(204)
        gatilho.disparar_workflow("dono/repo", "tok", "disparador.yml", "main", http=h)
        url, kw = h.chamadas[0]
        self.assertTrue(url.endswith("/repos/dono/repo/actions/workflows/disparador.yml/dispatches"))
        self.assertEqual(kw["json"], {"ref": "main"})
        self.assertEqual(kw["headers"]["Authorization"], "Bearer tok")
        with self.assertRaises(gatilho.ErroGatilho) as e:
            gatilho.disparar_workflow("dono/repo", "tok", http=Http(404))
        self.assertIn("404", str(e.exception))
        self.assertFalse(gatilho.configurado(lambda k, d="": ""))
        self.assertTrue(gatilho.configurado(lambda k, d="": "x"))


if __name__ == "__main__":
    unittest.main()


class TestAgendamento(unittest.TestCase):
    def test_campanha_agendada_so_entra_na_hora_marcada(self):
        from datetime import datetime, timedelta, timezone
        sb = fakes.FakeSupabase()
        futuro = datetime.now(timezone.utc) + timedelta(hours=2)
        camp = fila.criar_campanha(sb, "adm", "Agendada", "M", {"assunto": "a"}, CTX, 4, 8, False, registros(2), agendada_para=futuro)
        self.assertTrue(fila.esta_agendada(camp))
        self.assertEqual(fila.rotulo(camp), "🕘 Agendada")
        self.assertEqual(fila.candidatas(sb), [])
        self.assertEqual(len(fila.candidatas(sb, agora=futuro + timedelta(minutes=1))), 1)
        normal = fila.criar_campanha(sb, "adm", "Normal", "M", {"assunto": "a"}, CTX, 4, 8, False, registros(1))
        self.assertFalse(fila.esta_agendada(normal))
        self.assertEqual([c["nome"] for c in fila.candidatas(sb)], ["Normal"])
        self.assertNotIn("agendada_para", sb.tabelas["campanhas"][1])  # sem agendar, nada novo é gravado (banco antigo continua servindo)
