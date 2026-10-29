"""SMS pelo celular (gateway): regras do texto, cliente da API, fila, descadastro e trabalhador."""
import json
import unittest
from datetime import datetime, timedelta, timezone

from tests import fakes

fakes.instalar()

from core.utils import FUSO_BRASILIA  # noqa: E402
from disparador import sms, sms_banco as banco, sms_gateway, sms_worker as worker  # noqa: E402
from disparador.crypto import Cofre  # noqa: E402

CTX = {"empresa": "Empresa", "num_whatsapp": "5511999999999"}
SEGUNDA_10H = datetime(2026, 10, 26, 10, 0, tzinfo=FUSO_BRASILIA)  # segunda-feira
DOMINGO_10H = datetime(2026, 10, 25, 10, 0, tzinfo=FUSO_BRASILIA)


def reg(i, tel=None, **extra):
    return {"protocolo": f"P{i}", "nome": f"Ana Souza {i}", "email": f"c{i}@x.com",
            "telefone": tel if tel is not None else f"1198765{4000 + i}", **extra}


class Nuvem:
    """Servidor do app falso: guarda os pedidos e responde conforme o roteiro."""

    def __init__(self, respostas=None):
        self.pedidos, self.respostas = [], list(respostas or [])

    def __call__(self, req, timeout):
        corpo = json.loads(req.data.decode()) if req.data else None
        self.pedidos.append((req.get_method(), req.full_url, corpo))
        if self.respostas:
            status, resp = self.respostas.pop(0)
        else:
            status, resp = 202, {"id": f"m{len(self.pedidos)}", "state": "Pending"}
        return status, json.dumps(resp).encode()


class TestRegrasDoTexto(unittest.TestCase):
    def test_telefone_so_celular(self):
        self.assertEqual(sms.telefone_e164("(11) 98765-4321"), "+5511987654321")
        self.assertEqual(sms.telefone_e164("1133334444"), "")  # fixo
        self.assertEqual(sms.melhor_telefone("1133334444", "11987654321"), "+5511987654321")

    def test_texto_leva_frase_de_saida_sem_acentos_e_link(self):
        t = sms.montar_texto("Olá {nome}, protocolo {protocolo} {link}", reg(1), CTX)
        self.assertIn("Ana", t)
        self.assertIn("SAIR", t)
        self.assertIn("https://wa.me/5511999999999", t)
        self.assertNotIn("á", t)
        self.assertEqual(sms.partes(t)[2], "GSM")

    def test_acento_vira_unicode_e_alerta(self):
        self.assertEqual(sms.partes("olá")[2], "Unicode")
        self.assertTrue(sms.avisos_do_texto("olá " + "x" * 200))

    def test_triagem(self):
        self.assertEqual(sms.triar("", set(), set()), "Sem celular válido")
        self.assertIn("SMS", sms.triar("+5511987654321", {"5511987654321"}, set()))
        self.assertIn("e-mail", sms.triar("+5511987654321", set(), set(), email="A@x.com", emails_descadastrados={"a@x.com"}))
        self.assertIn("Já recebeu", sms.triar("+5511987654321", set(), {"P1|5511987654321"}, protocolo="P1"))
        self.assertEqual(sms.triar("+5511987654321", set(), {"P1|5511987654321"}, permitir_reenvio=True, protocolo="P1"), "")

    def test_janela(self):
        self.assertTrue(sms.limitar_janela(SEGUNDA_10H, 9, 19))
        self.assertFalse(sms.limitar_janela(SEGUNDA_10H.replace(hour=20), 9, 19))
        self.assertTrue(sms.limitar_janela(SEGUNDA_10H, None, None))


class TestClienteDaApi(unittest.TestCase):
    def gw(self, nuvem):
        return sms_gateway.Gateway("api.sms-gate.app", "u", "s", sim=2, abrir=nuvem)

    def test_envia_com_basic_sim_e_ttl(self):
        n = Nuvem()
        id_, estado = self.gw(n).enviar("+5511987654321", "oi")
        self.assertEqual((id_, estado), ("m1", "Pending"))
        metodo, url, corpo = n.pedidos[0]
        self.assertEqual((metodo, url), ("POST", "https://api.sms-gate.app/3rdparty/v1/messages"))
        self.assertEqual(corpo["phoneNumbers"], ["+5511987654321"])
        self.assertEqual(corpo["simNumber"], 2)
        self.assertEqual(corpo["ttl"], sms_gateway.TTL_PADRAO)

    def test_cai_para_caminho_antigo_no_404(self):
        n = Nuvem([(404, {}), (202, {"id": "x"})])
        self.assertEqual(self.gw(n).enviar("+5511987654321", "oi")[0], "x")
        self.assertTrue(n.pedidos[1][1].endswith("/3rdparty/v1/message"))

    def test_tipos_de_erro(self):
        casos = [(401, "credencial"), (403, "credencial"), (400, "numero"), (422, "numero"), (429, "temporario"),
                 (503, "temporario"), (500, "temporario")]
        for status, tipo in casos:
            with self.assertRaises(sms_gateway.ErroGateway) as c:
                self.gw(Nuvem([(status, {"message": "x"})])).enviar("+5511987654321", "oi")
            self.assertEqual(c.exception.tipo, tipo, status)
        self.assertEqual(c.exception.definitivo, False)

    def test_sem_rede_e_temporario(self):
        def cai(req, timeout):
            raise OSError("sem rede")
        with self.assertRaises(sms_gateway.ErroGateway) as c:
            sms_gateway.Gateway("", "u", "s", abrir=cai).enviar("+5511987654321", "oi")
        self.assertEqual(c.exception.tipo, "temporario")

    def test_testar_conexao(self):
        ok, msg = self.gw(Nuvem([(200, [{"id": "d1", "name": "Moto G"}])])).testar()
        self.assertTrue(ok)
        self.assertIn("Moto G", msg)
        ok, msg = self.gw(Nuvem([(200, [])])).testar()
        self.assertTrue(ok)
        self.assertIn("nenhum celular", msg)
        self.assertFalse(self.gw(Nuvem([(401, {})])).testar()[0])

    def test_criar_a_partir_da_linha(self):
        cofre = Cofre(None)
        self.assertIsNone(sms_gateway.criar({"senha": ""}, cofre))
        self.assertEqual(sms_gateway.criar({"senha": "abc", "usuario": "u"}, cofre).base, sms_gateway.URL_NUVEM)


class Base(unittest.TestCase):
    def setUp(self):
        self.sb = fakes.FakeSupabase(descadastros=[])
        self.cofre = Cofre(None)
        banco.criar_gateway(self.sb, self.cofre, "Chip 1", "", "user", "senha", None, 100)
        self.nuvem = Nuvem()
        self.pausas = []

    def campanha(self, registros, textos=("{nome}, protocolo {protocolo} {link}",), **kw):
        args = dict(delay_min=1, delay_max=2, janela=(9, 19), domingo=False, sem_acentos=True, permitir_reenvio=False)
        args.update(kw)
        return banco.criar_campanha(self.sb, "adm", "Teste", list(textos), CTX, registros=registros, **args)

    def rodar(self, agora=SEGUNDA_10H, minutos=14, relogio=None):
        r = relogio or (lambda: 0)
        camp = banco.candidatas(self.sb)[0]
        return worker.processar_campanha(self.sb, camp, self.cofre, prazo=minutos * 60, abrir=self.nuvem, relogio=r,
                                         dormir=lambda s: self.pausas.append(s), sortear=lambda a, b: a, agora=lambda: agora)

    def status(self):
        return {d["protocolo"]: d["status"] for d in self.sb.tabelas["sms_destinos"]}


class TestFila(Base):
    def test_criar_marca_sem_celular_e_repetidos(self):
        c = self.campanha([reg(1), reg(2, tel="1133334444"), reg(1), reg(3, tel="")])
        self.assertEqual(c["total"], 4)
        self.assertEqual(c["ignorados"], 3)
        st = [(d["protocolo"], d["status"], d["detalhe"]) for d in self.sb.tabelas["sms_destinos"]]
        self.assertEqual(st[0][1], "pendente")
        self.assertIn("Sem celular", st[1][2])
        self.assertIn("Repetido", st[2][2])

    def test_textos_sorteados_e_balanceados(self):
        self.campanha([reg(i) for i in range(10)], textos=["a {link}", "b {link}"])
        sorteados = [d["dados"]["_texto"] for d in self.sb.tabelas["sms_destinos"]]
        self.assertEqual(sorted(sorteados), [0] * 5 + [1] * 5)

    def test_agendada_so_entra_na_hora(self):
        futuro = datetime.now(timezone.utc) + timedelta(hours=3)
        c = self.campanha([reg(1)], agendada_para=futuro)
        self.assertTrue(banco.esta_agendada(c))
        self.assertEqual(banco.candidatas(self.sb), [])
        self.assertEqual(banco.rotulo(banco.obter(self.sb, c["id"])), banco.ROTULO["agendada"])
        self.assertEqual(len(banco.candidatas(self.sb, agora=futuro + timedelta(minutes=1))), 1)

    def test_descadastro_normaliza(self):
        self.assertEqual(banco.adicionar_descadastros(self.sb, ["(11) 98765-4321", "+55 11 98765-4321", "11 91234-5678", "lixo"]), 2)
        self.assertIn("5511987654321", banco.telefones_descadastrados(self.sb))
        banco.remover_descadastro(self.sb, "5511987654321")
        self.assertNotIn("5511987654321", banco.telefones_descadastrados(self.sb))

    def test_pausar_retomar_cancelar(self):
        c = self.campanha([reg(1)])
        banco.pausar(self.sb, c["id"])
        self.assertEqual(banco.obter(self.sb, c["id"])["status"], "pausada")
        banco.retomar(self.sb, c["id"])
        self.assertEqual(banco.obter(self.sb, c["id"])["status"], "pendente")
        banco.cancelar(self.sb, c["id"])
        self.assertEqual(banco.obter(self.sb, c["id"])["status"], "cancelada")

    def test_senha_protegida_e_ilegivel(self):
        from cryptography.fernet import Fernet
        bom = Cofre(Fernet.generate_key().decode())
        banco.criar_gateway(self.sb, bom, "Chip 2", "", "u2", "segredo", 1, 50)
        ativos, ruins = banco.carregar_gateways_ativos(self.sb, bom)
        self.assertEqual([g["nome"] for g in ativos], ["Chip 1", "Chip 2"])  # a pura de Chip 1 ainda é lida
        outro = Cofre(Fernet.generate_key().decode())
        ativos, ruins = banco.carregar_gateways_ativos(self.sb, outro)
        self.assertEqual([g["nome"] for g in ruins], ["Chip 2"])


class TestTrabalhador(Base):
    def test_envia_tudo_e_conclui(self):
        c = self.campanha([reg(i) for i in range(3)])
        self.assertEqual(self.rodar(), "concluida")
        self.assertEqual(set(self.status().values()), {"enviado"})
        self.assertEqual(len(self.nuvem.pedidos), 3)
        self.assertEqual(banco.obter(self.sb, c["id"])["enviados"], 3)
        self.assertEqual(len(self.sb.tabelas["sms_envios"]), 3)
        self.assertEqual(self.pausas, [1, 1, 1])  # intervalo entre SMS respeitado
        self.assertEqual(banco.enviados_hoje(self.sb), {self.sb.tabelas["sms_gateways"][0]["id"]: 3})

    def test_pula_sair_e_quem_ja_recebeu(self):
        banco.adicionar_descadastros(self.sb, ["+5511987654001"])
        self.campanha([reg(0), reg(1), reg(2)])
        self.sb.tabelas["sms_envios"] = [{"id": 1, "protocolo": "P2", "telefone": "+5511987654002", "status": "enviado"}]
        self.assertEqual(self.rodar(), "concluida")
        self.assertEqual(self.status(), {"P0": "enviado", "P1": "ignorado", "P2": "ignorado"})
        self.assertEqual(len(self.nuvem.pedidos), 1)

    def test_domingo_e_fora_da_janela(self):
        c = self.campanha([reg(1)])
        self.assertEqual(self.rodar(agora=DOMINGO_10H), "horario")
        self.assertIn("Domingo", banco.obter(self.sb, c["id"])["motivo"])
        self.assertEqual(self.rodar(agora=SEGUNDA_10H.replace(hour=21)), "horario")
        self.assertEqual(self.nuvem.pedidos, [])
        self.assertEqual(banco.obter(self.sb, c["id"])["status"], "pendente")  # continua sozinho depois
        self.assertEqual(self.rodar(agora=DOMINGO_10H), "horario")

    def test_domingo_liberado(self):
        self.campanha([reg(1)], domingo=True)
        self.assertEqual(self.rodar(agora=DOMINGO_10H), "concluida")

    def test_limite_diario_do_celular(self):
        self.sb.tabelas["sms_gateways"][0]["limite_diario"] = 2
        c = self.campanha([reg(i) for i in range(5)])
        self.assertEqual(self.rodar(), "limite")
        self.assertEqual(len(self.nuvem.pedidos), 2)
        self.assertEqual(banco.obter(self.sb, c["id"])["status"], "pendente")
        self.assertEqual(sum(1 for v in self.status().values() if v == "pendente"), 3)

    def test_rodizio_entre_celulares(self):
        banco.criar_gateway(self.sb, self.cofre, "Chip 2", "", "u2", "s2", None, 100)
        self.campanha([reg(i) for i in range(4)])
        self.rodar()
        usados = banco.enviados_hoje(self.sb)
        self.assertEqual(sorted(usados.values()), [2, 2])

    def test_senha_errada_pausa_sem_perder_ninguem(self):
        self.nuvem = Nuvem([(401, {})])
        c = self.campanha([reg(1), reg(2)])
        self.assertEqual(self.rodar(), "sem_celular")
        self.assertEqual(banco.obter(self.sb, c["id"])["status"], "pausada")
        self.assertEqual(set(self.status().values()), {"pendente"})
        self.assertEqual(self.sb.tabelas["sms_envios"], [])

    def test_sem_celular_cadastrado(self):
        self.sb.tabelas["sms_gateways"].clear()
        c = self.campanha([reg(1)])
        self.assertEqual(self.rodar(), "sem_celular")
        self.assertIn("Nenhum celular", banco.obter(self.sb, c["id"])["motivo"])

    def test_numero_recusado_vira_erro_e_cinco_seguidos_pausam(self):
        self.nuvem = Nuvem([(400, {"message": "numero invalido"})] * 5)
        c = self.campanha([reg(i) for i in range(8)])
        self.assertEqual(self.rodar(), "pausada")
        self.assertEqual(sum(1 for v in self.status().values() if v == "erro"), 5)
        self.assertEqual(sum(1 for v in self.status().values() if v == "pendente"), 3)
        self.assertEqual(banco.obter(self.sb, c["id"])["erros"], 5)

    def test_erro_temporario_volta_para_a_fila_e_passa_no_retry(self):
        self.nuvem = Nuvem([(429, {"retryAfter": 30})])
        self.campanha([reg(1), reg(2)])
        self.assertEqual(self.rodar(), "concluida")  # o 1 volta, é reenviado no laço seguinte
        self.assertEqual(set(self.status().values()), {"enviado"})
        self.assertIn(30, self.pausas)
        self.assertEqual(len(self.sb.tabelas["sms_envios"]), 2)

    def test_cancelar_no_meio_para_o_envio(self):
        c = self.campanha([reg(i) for i in range(5)])
        n = {"v": 0}

        def dormir(s):
            n["v"] += 1
            if n["v"] == 2:
                banco.cancelar(self.sb, c["id"])
        camp = banco.candidatas(self.sb)[0]
        r = worker.processar_campanha(self.sb, camp, self.cofre, 840, self.nuvem, lambda: 0, dormir, lambda a, b: a, lambda: SEGUNDA_10H)
        self.assertEqual(r, "cancelada")
        self.assertEqual(len(self.nuvem.pedidos), 2)
        self.assertEqual(banco.obter(self.sb, c["id"])["status"], "cancelada")

    def test_acabou_o_tempo_continua_depois(self):
        c = self.campanha([reg(i) for i in range(5)])
        hora = {"t": 0}

        def relogio():
            return hora["t"]

        def dormir(s):
            hora["t"] += 400  # cada SMS "demora" 400 s
        camp = banco.candidatas(self.sb)[0]
        r = worker.processar_campanha(self.sb, camp, self.cofre, 840, self.nuvem, relogio, dormir, lambda a, b: a, lambda: SEGUNDA_10H)
        self.assertEqual(r, "tempo")
        self.assertEqual(banco.obter(self.sb, c["id"])["status"], "pendente")
        self.assertEqual(sum(1 for v in self.status().values() if v == "enviado"), 3)
        self.assertNotIn("enviando", self.status().values())

    def test_recupera_interrompidos(self):
        c = self.campanha([reg(1), reg(2)])
        self.sb.tabelas["sms_destinos"][0]["status"] = "enviando"
        self.sb.tabelas["sms_destinos"][1]["status"] = "enviando"
        self.sb.tabelas["sms_envios"] = [{"id": 1, "protocolo": "P1", "telefone": "+5511987654001", "status": "enviado"}]
        self.assertEqual(self.rodar(), "concluida")
        self.assertEqual(len(self.nuvem.pedidos), 1)  # P1 já tinha saído: não repete
        self.assertEqual(self.status(), {"P1": "enviado", "P2": "enviado"})

    def test_sem_texto_pausa(self):
        c = self.campanha([reg(1)], textos=())
        self.assertEqual(self.rodar(), "pausada")

    def test_rodar_varias_campanhas_e_main(self):
        self.campanha([reg(1)])
        self.campanha([reg(2)])
        log = []
        houve, restante = worker.rodar(self.sb, self.cofre, 14, self.nuvem, lambda: 0, lambda s: None, lambda a, b: a, lambda: SEGUNDA_10H, log.append)
        self.assertTrue(houve)
        self.assertFalse(restante)
        self.assertEqual(len(log), 2)
        self.assertEqual(worker.main(env={}), 1)


if __name__ == "__main__":
    unittest.main()


class TestTelasSms(unittest.TestCase):
    """Executa todas as seções da tela de SMS com banco e Streamlit falsos (pega NameError, KeyError, erro de pandas)."""

    def setUp(self):
        from tests import test_ui_smoke as t
        self.t, self.ST = t, t.ST
        self.ST.session_state.clear()
        self.ST.respostas.clear()
        self.ST.avisos.clear()
        self.ST.secrets.clear()
        self.ST.secrets.update({"EMPRESA_NOME": "Empresa Teste", "WHATSAPP_NUMERO": "5511999999999"})
        self.ST.session_state["usuario"] = {"id": 1, "usuario": "adm", "nome_completo": "Chefe", "cargo": "ADM"}
        self.sb = t.banco()
        banco.criar_gateway(self.sb, Cofre(None), "Chip 1", "", "u", "s", 1, 100)
        banco.adicionar_descadastros(self.sb, ["11999990000"])
        c = banco.criar_campanha(self.sb, "adm", "Camp", ["oi {nome} {link}"], CTX, 20, 45, (9, 19), False, True, False,
                                 [reg(1), reg(2, tel="")])
        self.sb.tabelas["sms_envios"] = [{"id": 1, "data_hora": "2026-10-05T12:00:00+00:00", "nome": "A", "telefone": "+5511987654001",
                                          "protocolo": "P1", "gateway_nome": "Chip 1", "modelo": "Texto 1", "status": "enviado", "erro": "", "texto": "x"}]

    def abrir(self, secao):
        from disparador import ui
        self.ST.respostas["nav_email"] = "📱 SMS"
        self.ST.respostas["nav_sms"] = secao
        ui.renderizar_disparador(self.sb)
        self.assertFalse([a for a in self.ST.avisos if a[0] == "error"], (secao, self.ST.avisos))

    def test_todas_as_secoes_com_dados(self):
        for secao in ("✉️ Enviar", "⏱️ Fila", "📱 Celulares", "🚫 Sair", "📜 Histórico"):
            self.abrir(secao)

    def test_todas_as_secoes_sem_dados(self):
        self.sb = fakes.FakeSupabase()
        for secao in ("✉️ Enviar", "⏱️ Fila", "📱 Celulares", "🚫 Sair", "📜 Histórico"):
            self.abrir(secao)

    def test_cadastrar_celular_pela_tela(self):
        self.ST.respostas.update({"Nome do celular (ex.: Chip Vivo 1)": "Chip Novo", "Usuário (mostrado no app)": "usr",
                                  "Senha (mostrada no app)": "pwd", "➕ Salvar celular": True})
        from disparador import ui_sms
        try:
            ui_sms._celulares(self.sb)
        except fakes.Reiniciar:
            pass
        self.assertIn("Chip Novo", [g["nome"] for g in self.sb.tabelas["sms_gateways"]])

    def test_enviar_planilha_completa_ate_a_fila(self):
        import io
        import pandas as pd
        df = pd.DataFrame({"Protocolo": ["A1", "A2", "A3"], "Cliente": ["Ana Lima", "Bia Dias", "Caio Reis"],
                           "Celular": ["11 98765-1111", "(11) 98765-2222", "1133334444"], "Email": ["a@x.com", "b@x.com", "c@x.com"]})
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        buf.name, buf.size = "clientes.xlsx", len(buf.getvalue())
        self.ST.respostas.update({"sms_planilha": buf, "sms_revisado": True, "sms_fila_btn": True})
        from disparador import ui_sms
        ui_sms._pagina_enviar(self.sb)
        self.assertFalse([a for a in self.ST.avisos if a[0] == "error"], self.ST.avisos)
        camp = self.sb.tabelas["sms_campanhas"][-1]
        self.assertEqual(camp["total"], 3)
        self.assertEqual(camp["ignorados"], 1)  # o fixo
        self.assertEqual(camp["janela_ini"], 9)
        self.assertEqual(len(camp["textos"]), 3)


class TestConferirEntrega(unittest.TestCase):
    def test_atualiza_estado_dos_enviados(self):
        sb = fakes.FakeSupabase()
        cofre = Cofre(None)
        banco.criar_gateway(sb, cofre, "Chip 1", "", "u", "s")
        gid = sb.tabelas["sms_gateways"][-1]["id"]
        for i, est in enumerate([None, None, "Delivered"]):
            sb.tabelas.setdefault("sms_envios", []).append({"id": i + 1, "gateway_id": gid, "msg_id": f"m{i}", "status": "enviado",
                                                           "estado": est, "protocolo": f"P{i}", "telefone": "+55"})
        n = Nuvem([(200, {"state": "Delivered"}), (200, {"state": "Failed"})])
        cont = banco.atualizar_estados(sb, cofre, 100, abrir=n)
        self.assertEqual(cont, {"Delivered": 1, "Failed": 1})
        estados = {r["id"]: r["estado"] for r in sb.tabelas["sms_envios"]}
        self.assertEqual(sorted(estados.values()), ["Delivered", "Delivered", "Failed"])
        self.assertEqual(len(n.pedidos), 2)  # o que já estava 'Delivered' não é consultado de novo


class TestLoginPorToken(unittest.TestCase):
    """Se o servidor recusar o Basic, o cliente tenta o token JWT (método recomendado pelo app)."""

    def gw(self, nuvem):
        return sms_gateway.Gateway("", "PM7LK8", "senha", abrir=nuvem)

    def test_envio_usa_token_quando_o_basic_e_recusado(self):
        n = Nuvem([(401, {}), (201, {"access_token": "T0K", "token_type": "Bearer"}), (202, {"id": "m9", "state": "Pending"})])
        g = self.gw(n)
        self.assertEqual(g.enviar("+5511987654321", "oi")[0], "m9")
        self.assertIn("/auth/token", n.pedidos[1][1])
        self.assertEqual(n.pedidos[1][2]["scopes"][0], "messages:send")
        self.assertEqual(g._token, "T0K")

    def test_teste_de_conexao_com_token(self):
        n = Nuvem([(403, {}), (201, {"access_token": "T0K"}), (200, [{"id": "d1", "name": "Moto G"}])])
        ok, msg = self.gw(n).testar()
        self.assertTrue(ok)
        self.assertIn("Moto G", msg)

    def test_credencial_errada_mostra_codigos_http(self):
        n = Nuvem([(401, {}), (401, {"message": "bad"})])
        ok, msg = self.gw(n).testar()
        self.assertFalse(ok)
        self.assertIn("401", msg)
        self.assertIn("Cloud server", msg)

    def test_sem_token_mantem_o_erro_de_credencial(self):
        with self.assertRaises(sms_gateway.ErroGateway) as c:
            self.gw(Nuvem([(401, {}), (404, {})])).enviar("+5511987654321", "oi")
        self.assertEqual(c.exception.tipo, "credencial")
