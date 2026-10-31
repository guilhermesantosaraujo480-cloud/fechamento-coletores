"""Leitura de comprovantes de vale por IA: conferência do que a IA devolve, chamada ao Gemini e a tela de Vales."""
import io
import unittest
from datetime import date

from tests import fakes

ST = fakes.instalar()

from core import leitor_comprovante as leitor  # noqa: E402
from disparador import ia  # noqa: E402

HOJE = date(2026, 10, 30)


class TestConferencia(unittest.TestCase):
    def test_leitura_boa(self):
        r = leitor.interpretar({"tipo": "pix", "valor": "R$ 1.234,56", "data": "2026-10-29", "beneficiario": " ANA SOUZA ",
                                "id_transacao": "E1234-5678abc"}, HOJE)
        self.assertEqual(r["valor"], 1234.56)
        self.assertEqual(r["data"], date(2026, 10, 29))
        self.assertEqual(r["nome"], "ANA SOUZA")
        self.assertEqual(r["id_transacao"], "E12345678ABC")
        self.assertEqual(r["avisos"], [])

    def test_formatos_de_valor_e_data(self):
        for entrada, esperado in ((150, 150.0), (150.5, 150.5), ("150,50", 150.5), ("1.500", 1500.0), ("R$ 2.000,00", 2000.0), ("x", None), (None, None), (True, None)):
            self.assertEqual(leitor._numero(entrada), esperado, entrada)
        self.assertEqual(leitor._data("29/10/2026"), date(2026, 10, 29))
        self.assertIsNone(leitor._data("ontem"))

    def test_avisos(self):
        r = leitor.interpretar({"valor": -5, "data": "2027-01-01"}, HOJE)
        self.assertIsNone(r["valor"])
        self.assertIsNone(r["data"])  # futuro nunca é sugerido
        self.assertEqual(len(r["avisos"]), 2)
        self.assertTrue(leitor.interpretar({"valor": 999999, "data": "2026-10-01"}, HOJE)["avisos"])
        self.assertTrue(leitor.interpretar({"valor": 10, "data": "2024-01-01"}, HOJE)["avisos"])  # antiga

    def test_nao_e_comprovante_e_lixo(self):
        r = leitor.interpretar({"tipo": "nao_e_comprovante", "legivel": False}, HOJE)
        self.assertFalse(r["legivel"])
        self.assertIn("legível", r["avisos"][0])
        self.assertEqual(leitor.interpretar("texto solto", HOJE)["valor"], None)

    def test_id_curto_nao_vale(self):
        self.assertIsNone(leitor.normalizar_id("123"))  # evitaria "duplicado" falso
        self.assertEqual(leitor.normalizar_id("e123-4567 89"), "E123456789")


class Resp:
    def __init__(self, status, corpo):
        self.status_code, self._c = status, corpo

    def json(self):
        return self._c


class Http:
    def __init__(self, respostas):
        self.respostas, self.chamadas = list(respostas), []

    def post(self, url, **k):
        self.chamadas.append((url, k["json"]))
        return self.respostas.pop(0)

    def get(self, url, **k):
        return Resp(200, {"models": [{"name": "models/gemini-3-flash", "supportedGenerationMethods": ["generateContent"]}]})


def resposta_texto(texto):
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": texto}]}}]})


class TestChamadaGemini(unittest.TestCase):
    def test_envia_imagem_e_devolve_json(self):
        http = Http([resposta_texto('{"valor": 150.5, "data": "2026-10-29"}')])
        r = ia.ler_comprovante("chave", "", b"\xff\xd8fakejpeg", "leia", http)
        self.assertEqual(r["valor"], 150.5)
        partes = http.chamadas[0][1]["contents"][0]["parts"]
        self.assertEqual(partes[1]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(http.chamadas[0][1]["generationConfig"]["temperature"], 0)

    def test_lista_vira_primeiro_item_e_json_ruim_da_erro_claro(self):
        self.assertEqual(ia.ler_comprovante("c", "", b"x", "p", Http([resposta_texto('[{"valor": 1}]')]))["valor"], 1)
        with self.assertRaises(ia.ErroIA):
            ia.ler_comprovante("c", "", b"x", "p", Http([resposta_texto("isso não é json")]))
        with self.assertRaises(ia.ErroIA):
            ia.ler_comprovante("", "", b"x", "p", Http([]))

    def test_modelo_antigo_tenta_o_flash_atual_e_chave_ruim_avisa(self):
        http = Http([Resp(404, {}), resposta_texto('{"valor": 2}')])
        self.assertEqual(ia.ler_comprovante("c", "velho", b"x", "p", http)["valor"], 2)
        self.assertIn("gemini-3-flash", http.chamadas[1][0])
        with self.assertRaises(ia.ErroIA) as c:
            ia.ler_comprovante("c", "", b"x", "p", Http([Resp(403, {})]))
        self.assertIn("GEMINI_API_KEY", str(c.exception))


class Arquivo(io.BytesIO):
    name, size = "pix.jpg", 1234


def jpeg():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(b, "JPEG")
    return b.getvalue()


class TestTelaDeVales(unittest.TestCase):
    def setUp(self):
        ST.session_state.clear()
        ST.respostas.clear()
        ST.avisos.clear()
        ST.secrets.clear()
        ST.secrets["GEMINI_API_KEY"] = "chave"
        ST.session_state["usuario"] = {"id": 1, "usuario": "adm", "nome_completo": "Chefe", "cargo": "ADM"}
        from ui.adm import vales
        self.vales = vales
        self.original = vales.ia.ler_comprovante
        self.sb = fakes.FakeSupabase(vales_coleta=[], rota_apelidos=[], auditoria=[])
        self.arquivo = Arquivo(jpeg())
        ST.respostas["vale_foto_0"] = self.arquivo

    def tearDown(self):
        self.vales.ia.ler_comprovante = self.original

    def ler(self, bruto):
        self.vales.ia.ler_comprovante = lambda *a, **k: bruto
        ST.respostas["vale_ler"] = True
        self.vales._formulario(self.sb, ["Ana Souza", "Bia Lima"])

    def test_leitura_guarda_sugestao_e_identifica_o_coletor(self):
        self.ler({"tipo": "pix", "valor": 150.5, "data": "2026-10-29", "beneficiario": "ANA SOUZA", "id_transacao": "E1234567890"})
        leitura = ST.session_state["vale_ia"]
        self.assertEqual((leitura["valor"], leitura["coletor"]), (150.5, "Ana Souza"))
        self.assertEqual(ST.session_state["vale_form"], 1)  # campos recriados já preenchidos
        self.assertFalse([a for a in ST.avisos if a[0] == "error"])

    def test_ia_com_erro_nao_quebra_e_manda_preencher_a_mao(self):
        def falha(*a, **k):
            raise ia.ErroIA("Limite gratuito da IA atingido.")
        self.vales.ia.ler_comprovante = falha
        ST.respostas["vale_ler"] = True
        self.vales._formulario(self.sb, ["Ana Souza"])
        self.assertTrue([a for a in ST.avisos if a[0] == "warning" and "à mão" in a[1]])
        self.assertNotIn("vale_ia", ST.session_state)

    def test_sem_chave_explica_como_configurar(self):
        ST.secrets.clear()
        self.vales._formulario(self.sb, ["Ana Souza"])
        self.assertNotIn("vale_ia", ST.session_state)

    def test_lancar_grava_vale_com_codigo_da_transacao(self):
        self.ler({"valor": 80, "data": "2026-10-29", "beneficiario": "BIA LIMA", "id_transacao": "E9999999999"})
        ST.respostas.pop("vale_ler")
        ST.respostas.update({"Lançar vale": True, "vale_coletor_1": "Bia Lima", "vale_valor_1": 80.0})
        with self.assertRaises(fakes.Reiniciar):
            self.vales._formulario(self.sb, ["Ana Souza", "Bia Lima"])
        v = self.sb.tabelas["vales_coleta"][0]
        self.assertEqual((v["coletor"], v["valor_vale"], v["comprovante_id"]), ("Bia Lima", 80.0, "E9999999999"))
        self.assertEqual(ST.session_state["vale_up"], 1)  # o campo da foto é limpo

    def test_comprovante_repetido_e_bloqueado_ate_marcar_lancar_mesmo_assim(self):
        self.sb.tabelas["vales_coleta"].append({"id": 7, "data": "2026-10-20", "coletor": "Bia Lima", "valor_vale": 80.0, "comprovante_id": "E9999999999"})
        self.ler({"valor": 80, "data": "2026-10-29", "beneficiario": "BIA LIMA", "id_transacao": "E9999999999"})
        self.assertTrue(ST.session_state["vale_ia"]["duplicado"])
        ST.respostas.pop("vale_ler")
        ST.respostas["Lançar vale"] = True
        self.vales._formulario(self.sb, ["Ana Souza", "Bia Lima"])
        self.assertEqual(len(self.sb.tabelas["vales_coleta"]), 1)  # nada novo gravado
        self.assertTrue([a for a in ST.avisos if a[0] == "error" and "já foi lançado" in a[1]])

    def test_sem_a_coluna_nova_o_vale_ainda_e_lancado(self):
        self.ler({"valor": 30, "data": "2026-10-29", "beneficiario": "ANA SOUZA", "id_transacao": "E1111111111"})
        ST.respostas.pop("vale_ler")
        ST.respostas["Lançar vale"] = True
        original = self.sb.table

        def tabela(nome):
            t = original(nome)
            if nome == "vales_coleta":
                inserir = t.insert
                t.insert = lambda p: (_ for _ in ()).throw(RuntimeError("column comprovante_id does not exist")) if "comprovante_id" in p else inserir(p)
            return t
        self.sb.table = tabela
        with self.assertRaises(fakes.Reiniciar):
            self.vales._formulario(self.sb, ["Ana Souza", "Bia Lima"])
        self.assertEqual(len(self.sb.tabelas["vales_coleta"]), 1)
        self.assertNotIn("comprovante_id", self.sb.tabelas["vales_coleta"][0])


if __name__ == "__main__":
    unittest.main()
