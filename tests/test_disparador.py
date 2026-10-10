import smtplib
import unittest
from io import BytesIO

import pandas as pd

import tests  # noqa: F401
from disparador import campanha, colunas, ia, metricas, planilha, templates
from disparador.crypto import Cofre
from disparador.envio_smtp import GerenteSMTP, conta_esgotada, escolher_conta
from disparador.utils import email_valido, separar_emails

CTX = {"empresa": "Empresa <X>", "identificacao": "CNPJ 1", "valor_multa": "", "url_clique": "", "num_whatsapp": "5511999999999"}
MODELO = {"tipo": "db", "nome": "m", "assunto": "Oi {nome} {protocolo}", "texto": "Olá {nome}\nProtocolo {protocolo}", "regras": ""}


def planilha_exemplo(linhas):
    return pd.DataFrame(linhas, columns=["BA", "Cliente", "E-mail", "Endereço", "Número", "Bairro", "Cep"])


class TestColunas(unittest.TestCase):
    def test_detecta_com_acento_e_variacoes(self):
        df = planilha_exemplo([])
        m = colunas.detectar_colunas(df)
        self.assertEqual((m["protocolo"], m["nome"], m["email"], m["endereco"], m["numero"]),
                         ("BA", "Cliente", "E-mail", "Endereço", "Número"))
        self.assertIsNone(m["tipo"])

    def test_registro_limpa_nan_e_float(self):
        df = planilha_exemplo([[123.0, None, "A@B.com ", "Rua 1", 5.0, float("nan"), "00000"]])
        reg = colunas.registro_da_linha(df.iloc[0], colunas.detectar_colunas(df))
        self.assertEqual((reg["protocolo"], reg["nome"], reg["email"], reg["numero"]), ("123", "", "a@b.com", "5"))
        self.assertEqual(colunas.montar_endereco(reg), "Rua 1 - Nº 5 - CEP: 00000")


class TestTemplates(unittest.TestCase):
    def test_html_escapa_dados_do_cliente(self):
        reg = {"nome": "<script>alert(1)</script>", "protocolo": "1", "email": "a@b.com", "endereco": "", "numero": "", "bairro": "", "cep": "", "tipo": ""}
        d = templates.preparar_dados(reg, MODELO, CTX, "x")
        self.assertNotIn("<script>", d["html"])
        self.assertIn("Empresa &lt;X&gt;", d["html"])
        self.assertIn("SAIR", d["texto"])

    def test_assunto_e_link(self):
        reg = {"nome": "Ana", "protocolo": "77", "email": "a@b.com", "endereco": "R", "numero": "", "bairro": "", "cep": "", "tipo": ""}
        d = templates.preparar_dados(reg, MODELO, {**CTX, "url_clique": "https://f.test/c"}, "ENV1")
        self.assertEqual(d["assunto"], "Oi Ana 77")
        self.assertIn("https://f.test/c?protocolo=77&amp;envio=ENV1&amp;dest=", d["html"])

    def test_multa_so_aparece_se_configurada(self):
        reg = {"nome": "A", "protocolo": "1", "email": "a@b.com", "endereco": "", "numero": "", "bairro": "", "cep": "", "tipo": "Involuntário"}
        padrao = {"tipo": "padrao1"}
        self.assertNotIn("R$", templates.preparar_dados(reg, padrao, CTX, "x")["html"])
        self.assertIn("R$ 385", templates.preparar_dados(reg, padrao, {**CTX, "valor_multa": "R$ 385"}, "x")["html"])

    def test_mensagem_multipart(self):
        reg = {"nome": "A", "protocolo": "1", "email": "a@b.com", "endereco": "", "numero": "", "bairro": "", "cep": "", "tipo": ""}
        msg = templates.construir_mensagem({"email": "c@g.com", "nome_remetente": ""}, "a@b.com", templates.preparar_dados(reg, MODELO, CTX, "x"), "Emp")
        self.assertTrue(msg.is_multipart())
        self.assertIn("List-Unsubscribe", msg)


class FakeSMTP:
    def __init__(self, falhar=None):
        self.enviadas, self.falhar = [], falhar

    def send_message(self, msg):
        if self.falhar:
            raise self.falhar
        self.enviadas.append(msg["To"])

    def quit(self):
        pass


class TestCampanha(unittest.TestCase):
    def rodar(self, linhas, contas=None, enviados=None, falhar=None, ja=(), desc=(), parar=lambda: False, reenvio=False):
        df = planilha_exemplo(linhas)
        smtp = FakeSMTP(falhar)
        contas = contas or [{"email": "c1@g.com", "_senha": "x", "limite_diario": 100}]
        ger = GerenteSMTP(fabrica=lambda e, s: smtp)
        gravados = []
        resumo = campanha.executar_campanha(
            df, colunas.detectar_colunas(df), contas, enviados if enviados is not None else {}, set(desc), set(ja), ger,
            campanha.Parametros(MODELO, "m", CTX, 1, 2, reenvio),
            registrar=lambda *a: gravados.append(a) or True, parar=parar, dormir=lambda s: None)
        return resumo, smtp, gravados

    def test_envia_pula_invalidos_duplicados_descadastrados_e_ja_enviados(self):
        linhas = [[1, "A", "a@x.com", "", "", "", ""], [1, "A", "a@x.com", "", "", "", ""], [2, "B", "email@email.com", "", "", "", ""],
                  [3, "C", "c@x.com", "", "", "", ""], [4, "D", "d@x.com", "", "", "", ""], [5, "E", "e@x.com", "", "", "", ""]]
        r, smtp, gravados = self.rodar(linhas, ja={"4|d@x.com"}, desc={"c@x.com"})
        self.assertEqual((r.sucessos, r.ignorados, r.erros), (2, 4, 0))
        self.assertEqual(smtp.enviadas, ["a@x.com", "e@x.com"])
        self.assertEqual(len(gravados), 2)

    def test_reenvio_permitido(self):
        r, _, _ = self.rodar([[4, "D", "d@x.com", "", "", "", ""]], ja={"4|d@x.com"}, reenvio=True)
        self.assertEqual(r.sucessos, 1)

    def test_respeita_limite_diario(self):
        contas = [{"email": "c1@g.com", "_senha": "x", "limite_diario": 2}]
        linhas = [[i, "N", f"p{i}@x.com", "", "", "", ""] for i in range(5)]
        r, smtp, _ = self.rodar(linhas, contas, enviados={"c1@g.com": 1})
        self.assertEqual(r.sucessos, 1)
        self.assertIn("Limite diário", r.motivo_parada)

    def test_aborta_apos_5_erros_seguidos(self):
        linhas = [[i, "N", f"p{i}@x.com", "", "", "", ""] for i in range(20)]
        r, _, gravados = self.rodar(linhas, falhar=RuntimeError("boom"))
        self.assertEqual(r.erros, 5)
        self.assertIn("5 erros seguidos", r.motivo_parada)
        self.assertTrue(all(g[4] == "erro" for g in gravados))

    def test_conta_bloqueada_sai_do_rodizio(self):
        contas = [{"email": "c1@g.com", "_senha": "x", "limite_diario": 100}, {"email": "c2@g.com", "_senha": "x", "limite_diario": 100}]
        enviados = {}
        r, _, _ = self.rodar([[i, "N", f"p{i}@x.com", "", "", "", ""] for i in range(3)], contas, enviados,
                             falhar=smtplib.SMTPAuthenticationError(535, b"bad"))
        self.assertTrue(any("bloqueada" in a for a in r.avisos))
        self.assertEqual(enviados.get("c1@g.com"), 10 ** 9)

    def test_parar(self):
        r, smtp, _ = self.rodar([[i, "N", f"p{i}@x.com", "", "", "", ""] for i in range(3)], parar=lambda: True)
        self.assertEqual(r.sucessos, 0)
        self.assertIn("interrompido", r.motivo_parada)

    def test_rodizio_e_esgotada(self):
        contas = [{"email": "a", "limite_diario": 1}, {"email": "b", "limite_diario": 1}]
        c, p = escolher_conta(contas, {}, 0)
        self.assertEqual((c["email"], p), ("a", 1))
        self.assertEqual(escolher_conta(contas, {"a": 1}, 0)[0]["email"], "b")
        self.assertIsNone(escolher_conta(contas, {"a": 1, "b": 1}, 0)[0])
        self.assertTrue(conta_esgotada(RuntimeError("550 5.4.5 Daily user sending limit exceeded")))
        self.assertFalse(conta_esgotada(RuntimeError("timeout")))


class TestPlanilhaEUtils(unittest.TestCase):
    def test_csv_latin1_com_ponto_e_virgula(self):
        arq = BytesIO("BA;Cliente;Email\n1;José;j@x.com\n2;Maria;m@x.com\n".encode("latin1"))
        arq.name = "dados.csv"
        df = planilha.carregar_dataframe(arq)
        self.assertEqual(list(df["Cliente"]), ["José", "Maria"])

    def test_relatorio_previo(self):
        df = planilha_exemplo([[1, "A", "a@x.com", "", "", "", ""], [1, "A", "a@x.com", "", "", "", ""], [2, "B", "ruim", "", "", "", ""]])
        rel = planilha.relatorio_previo(df, colunas.detectar_colunas(df), set(), set())
        self.assertEqual((rel.total, rel.enviaveis), (3, 1))

    def test_emails(self):
        self.assertFalse(email_valido("teste@teste.com"))
        self.assertTrue(email_valido("a@b.co"))
        self.assertEqual(separar_emails("A@x.com; b@y.com\nlixo"), {"a@x.com", "b@y.com"})


class TestCofreEIA(unittest.TestCase):
    def test_cofre(self):
        from cryptography.fernet import Fernet
        c = Cofre(Fernet.generate_key().decode())
        enc = c.proteger("senha app")
        self.assertTrue(enc.startswith("enc:"))
        self.assertEqual(c.revelar(enc), "senha app")
        self.assertEqual(c.revelar("antiga"), "antiga")
        self.assertEqual(Cofre("").revelar(enc), "")
        self.assertEqual(Cofre("").proteger("x"), "x")
        self.assertEqual(Cofre(Fernet.generate_key().decode()).revelar(enc), "")

    def test_ia(self):
        class R:
            def __init__(self, code, js=None):
                self.status_code, self._js = code, js

            def json(self):
                return self._js

        corpo = {"candidates": [{"content": {"parts": [{"text": '```json\n[{"assunto":"A {protocolo}","texto":"Oi {nome}"}]\n```'}]}}]}
        class Http:
            def __init__(self, r): self.r = r
            def post(self, *a, **k): return self.r
            def get(self, *a, **k): return R(200, {"models": [{"name": "models/g1", "supportedGenerationMethods": ["generateContent"]}, {"name": "models/e", "supportedGenerationMethods": ["embed"]}]})
        self.assertEqual(ia.gerar_modelos_ia("k", "m", "s", "t", 1, http=Http(R(200, corpo)))[0]["assunto"], "A {protocolo}")
        with self.assertRaises(ia.ErroIA) as e:
            ia.gerar_modelos_ia("k", "m", "s", "t", 1, http=Http(R(429)))
        self.assertIn("Limite", str(e.exception))
        with self.assertRaises(ia.ErroIA):
            ia.gerar_modelos_ia("", "m", "s", "t", 1)
        self.assertEqual(ia.listar_modelos_gemini("k", http=Http(None)), ["g1"])

    def test_avisos(self):
        self.assertTrue(any("R$" in a for a in ia.avisos_do_modelo("x {nome} {protocolo}", "multa de R$ 100")))
        self.assertEqual(ia.avisos_do_modelo("{protocolo}", "oi {nome}"), [])
        self.assertTrue(any("desconhecidos" in a for a in ia.avisos_do_modelo("{protocolo}", "oi {nome} {x}")))


class TestMetricas(unittest.TestCase):
    def test_robos_x_pessoas(self):
        cliques = pd.DataFrame([
            {"envio_id": "e1", "data_hora": "2026-10-10T10:00:00+00:00", "user_agent": "Mozilla/5.0 (iPhone)"},
            {"envio_id": "e2", "data_hora": "2026-10-10T10:00:01+00:00", "user_agent": "GoogleImageProxy"},
            {"envio_id": "e3", "data_hora": "2026-10-10T10:00:05+00:00", "user_agent": "Mozilla"},
            {"envio_id": "e3", "data_hora": "2026-10-10T10:00:06+00:00", "user_agent": "Mozilla"},
            {"envio_id": "e3", "data_hora": "2026-10-10T10:00:07+00:00", "user_agent": "Mozilla"},
            {"envio_id": "e4", "data_hora": "2026-10-10T10:00:08+00:00", "user_agent": "Mozilla"},
        ])
        envios = pd.DataFrame([{"envio_id": "e4", "data_hora": "2026-10-10T10:00:00+00:00"},
                               {"envio_id": "e1", "data_hora": "2026-10-10T09:00:00+00:00"}])
        c = metricas.classificar_cliques(cliques, envios)
        self.assertEqual(list(c["perfil"]), ["Pessoa", "Robô", "Robô", "Robô", "Robô", "Robô"])
        r = metricas.resumir(c, total_enviados=10)
        self.assertEqual((r.pessoas, r.robos, r.envios_com_pessoa, r.taxa_pessoas), (1, 5, 1, 10.0))

    def test_sem_colunas_extras_nao_quebra(self):
        c = metricas.classificar_cliques(pd.DataFrame([{"envio_id": "a"}]))
        self.assertEqual(metricas.resumir(c).pessoas, 1)
        self.assertEqual(metricas.resumir(metricas.classificar_cliques(pd.DataFrame())).total, 0)


if __name__ == "__main__":
    unittest.main()
