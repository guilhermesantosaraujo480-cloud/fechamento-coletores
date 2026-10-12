import io
import unittest

import pandas as pd

from tests import fakes

ST = fakes.instalar()

from rotas import envio, leitura, mensagens, perfis as pf, processamento as pr, vinculos  # noqa: E402
from rotas import whatsapp as wa  # noqa: E402


def df_reintegra():
    return pd.DataFrame({
        "BA": ["1", "2", "3", "4"], "Cliente": ["Ana", "Beto", "Caio", "Dani"],
        "Endereço": ["Rua A", "Rua B", "Rua C", "Rua A"], "Número": ["10.0", "5", "", "10"],
        "Bairro": ["Centro", "Centro", "Lapa", "Centro"], "Cep": ["1310000", "01310-001", "x", "1310000"],
        "Cidade": ["SP"] * 4, "UF": ["SP"] * 4, "Telefone 1": ["11987654321", "5511987654322", "", "1133334444"],
        "Complemento": [""] * 4})


def df_tim():
    return pd.DataFrame({
        "Número do Pedido": ["9", "8"], "Conta.2": ["c1", "c2"], "Nome": ["X", "Y"], "Logradouro": ["Rua Z", "Rua W"],
        "Número": ["1", "2"], "Bairro": ["B1", "B2"], "CEP": ["01000000", "02000000"], "Cidade": ["SP", "SP"],
        "Telefone": ["", "11911112222"], "Celular": ["11922223333", ""], "Informação adicional": ["", ""], "UF": ["SP", "SP"]})


class TestPerfis(unittest.TestCase):
    def test_deteccao(self):
        self.assertEqual(pf.detectar_perfil(list(df_reintegra().columns), pf.PERFIS_PADRAO).nome, pf.REINTEGRA.nome)
        self.assertEqual(pf.detectar_perfil(list(df_tim().columns), pf.PERFIS_PADRAO).nome, pf.TIM_CSS.nome)
        self.assertIsNone(pf.detectar_perfil(["a", "b"], pf.PERFIS_PADRAO))

    def test_dict_roundtrip(self):
        p = pf.Perfil.de_dict(pf.TIM_CSS.para_dict())
        self.assertEqual(p.mapa, pf.TIM_CSS.mapa)


class TestProcessamento(unittest.TestCase):
    def test_telefone_cep(self):
        self.assertEqual(pr.normalizar_telefone("5511987654321"), ("(11) 98765-4321", True))
        self.assertEqual(pr.normalizar_telefone("1133334444"), ("(11) 3333-4444", True))
        self.assertFalse(pr.normalizar_telefone("123")[1])
        self.assertEqual(pr.normalizar_cep("1310000"), ("01310-000", True))
        self.assertFalse(pr.normalizar_cep("x")[1])
        self.assertEqual(pr.numero_whatsapp("(11) 98765-4321"), "5511987654321")
        self.assertEqual(pr.numero_whatsapp(""), "")
        self.assertEqual(pr.numero_whatsapp("5511987654321"), "5511987654321")

    def test_reintegra(self):
        can, falt = pr.aplicar_perfil(df_reintegra(), pf.REINTEGRA)
        self.assertEqual(falt, [])
        self.assertEqual(can["endereco_completo"].iloc[0], "Rua A N° 10")
        self.assertEqual(can["endereco_completo"].iloc[2], "Rua C")
        probs = pr.checar_qualidade(can)
        self.assertIn("Sem telefone válido", set(probs["Problema"]))
        self.assertIn("CEP inválido", set(probs["Problema"]))
        saida = pr.montar_saida(can, pf.REINTEGRA)
        self.assertEqual(list(saida.columns)[:3], [c for c, _ in pf.REINTEGRA.saida][:3])
        self.assertIn("Mapa", saida.columns)

    def test_tim_e_celular_vale(self):
        can, falt = pr.aplicar_perfil(df_tim(), pf.TIM_CSS)
        self.assertEqual(falt, [])
        self.assertTrue(can["tel_ok"].all())  # telefone OU celular

    def test_coluna_faltando(self):
        _, falt = pr.aplicar_perfil(df_reintegra().drop(columns=["Bairro"]), pf.REINTEGRA)
        self.assertEqual(falt, ["Bairro"])

    def test_divisao_equilibrada(self):
        n = 60
        df = pd.DataFrame({"BA": range(n), "Cliente": ["c"] * n, "Endereço": ["r"] * n, "Número": ["1"] * n,
                           "Bairro": [f"B{i % 12}" for i in range(n)], "Cep": ["01000000"] * n, "Cidade": ["SP"] * n,
                           "UF": ["SP"] * n, "Telefone 1": ["11987654321"] * n, "Complemento": [""] * n})
        can, _ = pr.aplicar_perfil(df, pf.REINTEGRA)
        atrib = pr.dividir_entre(can, ["A", "B", "C"])
        cont = atrib.value_counts()
        self.assertEqual(set(cont.index), {"A", "B", "C"})
        self.assertLessEqual(cont.max() - cont.min(), 10)
        self.assertEqual(len(atrib), n)
        # bairro gigante é repartido
        can["bairro"] = "UNICO"
        self.assertEqual(pr.dividir_entre(can, ["A", "B"]).nunique(), 2)
        self.assertTrue((pr.dividir_entre(can, []) == pr.SEM_COLETOR).all())

    def test_leitura_tab_latin1_e_excel(self):
        txt = "BA\tCliente\tEndereço\nx\tJosé\tRua\n".encode("latin1")
        class Arq(io.BytesIO):
            name = "a.xls"
        df = leitura.carregar_planilha(Arq(txt))
        self.assertEqual(df["Cliente"].iloc[0], "José")
        buf = Arq()
        buf.name = "a.xlsx"
        df_tim().to_excel(buf, index=False)
        buf.seek(0)
        self.assertEqual(leitura.carregar_planilha(buf)["Conta.2"].iloc[1], "c2")


class TestVinculos(unittest.TestCase):
    def test_sugestao(self):
        rota = [{"id": 1, "nome_rota": "GABRIEL", "usuario_id": None}, {"id": 2, "nome_rota": "RENILTON", "usuario_id": None},
                {"id": 3, "nome_rota": "CARLOS", "usuario_id": 9}]
        us = [{"id": 5, "usuario": "gabriel.s", "nome_completo": "Gabriel Souza", "cargo": "COLETOR"},
              {"id": 6, "usuario": "adm", "nome_completo": "Gabriel Chefe", "cargo": "ADM"},
              {"id": 9, "usuario": "carlos", "nome_completo": "Carlos", "cargo": "COLETOR"}]
        self.assertEqual([(c, u) for c, u, _ in vinculos.sugerir_vinculos(rota, us)], [(1, 5)])


class TestMensagem(unittest.TestCase):
    def test_limite(self):
        n = 300
        df = pd.DataFrame({"BA": range(n), "Cliente": ["c"] * n, "Endereço": ["r"] * n, "Número": ["1"] * n,
                           "Bairro": [f"Bairro numero {i}" for i in range(n)], "Cep": [""] * n, "Cidade": ["SP"] * n,
                           "UF": ["SP"] * n, "Telefone 1": [""] * n, "Complemento": [""] * n})
        can, _ = pr.aplicar_perfil(df, pf.REINTEGRA)
        from datetime import date
        self.assertLessEqual(len(mensagens.mensagem_rota("Reintegra", "GABRIEL", date(2026, 10, 10), can)), 900)
        self.assertLessEqual(len(mensagens.lista_para_copiar("Reintegra", "G", date(2026, 10, 10), can)), 3600)


class Resp:
    def __init__(self, status=200, corpo=None):
        self.status_code, self._c, self.text = status, corpo if corpo is not None else {}, ""

    def json(self):
        return self._c


class Http:
    def __init__(self, status=200, corpo=None):
        self.chamadas, self.status, self.corpo = [], status, corpo

    def _f(self, metodo):
        def f(url, **kw):
            self.chamadas.append((metodo, url, kw))
            return Resp(self.status, self.corpo)
        return f

    def __getattr__(self, m):
        return self._f(m)


class TestWhats(unittest.TestCase):
    def test_evolution(self):
        h = Http()
        g = wa.Evolution("https://e.test/", "inst", "KEY", http=h)
        g.enviar_texto("123@g.us", "oi")
        g.enviar_arquivo("123@g.us", b"abc", "r.xlsx", "leg")
        m, url, kw = h.chamadas[1]
        self.assertEqual(url, "https://e.test/message/sendMedia/inst")
        self.assertEqual(kw["headers"]["apikey"], "KEY")
        self.assertEqual(kw["json"]["fileName"], "r.xlsx")

    def test_zapi_e_erro(self):
        h = Http()
        wa.ZApi("https://z.test/instances/1/token/2", "CT", http=h).enviar_texto("5511", "x")
        self.assertEqual(h.chamadas[0][2]["headers"]["Client-Token"], "CT")
        with self.assertRaises(wa.ErroWhats):
            wa.Evolution("https://e.test", "i", "k", http=Http(401, {"e": "x"})).enviar_texto("1", "x")

    def test_criar_gateway(self):
        self.assertIsNone(wa.criar_gateway(lambda k, d="": d))
        cfg = {"WHATS_PROVEDOR": "zapi", "WHATS_API_URL": "https://z"}
        self.assertIsInstance(wa.criar_gateway(lambda k, d="": cfg.get(k, d)), wa.ZApi)

    def test_envio_aborta_apos_3_erros(self):
        class G:
            def __init__(self, falha):
                self.falha, self.n = falha, 0

            def enviar_arquivo(self, *a):
                self.n += 1
                if self.falha:
                    raise wa.ErroWhats("x")
        pacotes = [{"coletor": f"C{i}", "conteudo": b"", "arquivo": "a", "mensagem": "m", "telefone": ""} for i in range(5)]
        reg = []
        g = G(True)
        res, parada = envio.enviar_rotas(g, pacotes, ["g1"], lambda r, p: reg.append(r), dormir=lambda s: None)
        self.assertEqual(len(res), 3)
        self.assertTrue(parada)
        g = G(False)
        res, parada = envio.enviar_rotas(g, pacotes, ["g1", "g2"], lambda r, p: None, dormir=lambda s: None)
        self.assertEqual((len(res), parada), (10, ""))
        pacotes[0]["telefone"] = "5511"
        res, _ = envio.enviar_rotas(G(False), pacotes[:1], ["g1"], lambda r, p: None, individual=True, dormir=lambda s: None)
        self.assertEqual(len(res), 2)


if __name__ == "__main__":
    unittest.main()
