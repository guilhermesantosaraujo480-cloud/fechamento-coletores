"""Falhas de rede: tentativas automáticas, rede de segurança geral e proteção de telas."""
import unittest

from tests import fakes

ST = fakes.instalar()


class ErroDeRede(Exception):
    pass


class ConnectTimeout(Exception):
    pass


class TestResiliencia(unittest.TestCase):
    def test_reconhece_falhas_de_rede(self):
        from core.resiliencia import eh_transitorio
        for e in (ConnectionError(), TimeoutError(), ConnectTimeout("x"), RuntimeError("Server disconnected without sending a response")):
            self.assertTrue(eh_transitorio(e), e)
        for e in (ValueError("x"), KeyError("a"), RuntimeError("duplicate key value violates unique constraint")):
            self.assertFalse(eh_transitorio(e), e)

    def test_repete_e_depois_funciona(self):
        from core.resiliencia import com_tentativas
        chamadas = []

        def op():
            chamadas.append(1)
            if len(chamadas) < 3:
                raise ConnectTimeout("queda")
            return "ok"
        self.assertEqual(com_tentativas(op, dormir=lambda s: None), "ok")
        self.assertEqual(len(chamadas), 3)

    def test_desiste_depois_do_limite_e_nao_repete_erro_comum(self):
        from core.resiliencia import com_tentativas
        n = []
        with self.assertRaises(ConnectTimeout):
            com_tentativas(lambda: (n.append(1), (_ for _ in ()).throw(ConnectTimeout("x")))[1], tentativas=3, dormir=lambda s: None)
        self.assertEqual(len(n), 3)
        m = []
        with self.assertRaises(ValueError):
            com_tentativas(lambda: (m.append(1), (_ for _ in ()).throw(ValueError("x")))[1], dormir=lambda s: None)
        self.assertEqual(len(m), 1)

    def test_upload_usa_upsert_e_tenta_de_novo(self):
        from core import armazenamento
        tentativas = []

        class Bucket:
            def upload(self, path, file, file_options=None):
                tentativas.append(file_options)
                if len(tentativas) == 1:
                    raise ConnectTimeout("caiu")

        class Sb:
            class storage:
                @staticmethod
                def from_(b):
                    return Bucket()
        import core.resiliencia as r
        original = r.time.sleep
        r.time.sleep = lambda s: None
        try:
            caminho = armazenamento.enviar_foto_pronta(Sb(), b"x", None, "coleta_ana")
        finally:
            r.time.sleep = original
        self.assertTrue(caminho.endswith(".jpg"))
        self.assertEqual(len(tentativas), 2)
        self.assertEqual(tentativas[0]["upsert"], "true")


class TestRedeDeSeguranca(unittest.TestCase):
    def setUp(self):
        ST.session_state.clear(); ST.respostas.clear(); ST.avisos.clear()
        ST.session_state["usuario"] = {"id": 2, "usuario": "ana", "nome_completo": "Ana", "cargo": "COLETOR"}

    def test_erro_vira_mensagem_amigavel_sem_detalhe_para_coletor(self):
        from ui import falhas

        def quebra():
            raise RuntimeError("segredo tecnico xyz")
        falhas.rodar_protegido(quebra, obter_sb=lambda: fakes.FakeSupabase(auditoria=[]))
        texto = " ".join(a[1] for a in ST.avisos)
        self.assertIn("Tentar novamente", texto)
        self.assertNotIn("segredo tecnico", texto)

    def test_rerun_e_stop_passam_direto(self):
        from ui import falhas

        def rerun():
            raise fakes.Reiniciar()
        with self.assertRaises(fakes.Reiniciar):
            falhas.rodar_protegido(rerun)
        with self.assertRaises(fakes.Parar):
            falhas.rodar_protegido(lambda: (_ for _ in ()).throw(fakes.Parar()))

    def test_falha_e_registrada_na_auditoria(self):
        from ui import falhas
        sb = fakes.FakeSupabase(auditoria=[])
        falhas.rodar_protegido(lambda: (_ for _ in ()).throw(RuntimeError("x")), obter_sb=lambda: sb)
        self.assertEqual(sb.tabelas["auditoria"][0]["acao"], "falha_inesperada")

    def test_funciona_mesmo_se_nao_ha_banco(self):
        from ui import falhas
        falhas.rodar_protegido(lambda: (_ for _ in ()).throw(RuntimeError("x")), obter_sb=lambda: None)
        self.assertTrue(ST.avisos)


if __name__ == "__main__":
    unittest.main()


class TestEnvioIdempotente(unittest.TestCase):
    def linha(self):
        return {"data": "2026-11-03", "coletor": "Ana", "quantidade": 2, "foto_url": "f_m.jpg", "status": "Pendente", "pago": False, "valor_total": 20.0}

    def test_queda_depois_de_gravar_nao_da_erro_nem_duplica(self):
        from core import envio

        class Sb(fakes.FakeSupabase):
            falhou = False

            def table(self, nome):
                c = super().table(nome)
                if nome == "coletas":
                    original = c.execute

                    def execute():
                        r = original()
                        if c.op == "insert" and not Sb.falhou:
                            Sb.falhou = True
                            raise ConnectionError("resposta perdida")  # gravou, mas a resposta caiu
                        return r
                    c.execute = execute
                return c
        sb = Sb(coletas=[])
        self.assertTrue(envio.registrar_coleta(sb, self.linha(), "chave1"))
        self.assertEqual(len(sb.tabelas["coletas"]), 1)

    def test_erro_real_continua_erro(self):
        from core import envio
        sb = fakes.FakeSupabase(coletas=[])
        sb.falhar_em.add("coletas")
        with self.assertRaises(RuntimeError):
            envio.registrar_coleta(sb, self.linha(), "chave2")

    def test_tela_reaproveita_chave_e_arquivo_nas_tentativas(self):
        import io
        from PIL import Image
        from tests.test_ui_smoke import banco
        ST.session_state.clear(); ST.respostas.clear(); ST.avisos.clear(); ST.secrets["EMPRESA_NOME"] = "E"
        ST.session_state["usuario"] = {"id": 2, "usuario": "ana", "nome_completo": "Ana", "cargo": "COLETOR"}
        b = io.BytesIO(); Image.effect_noise((400, 300), 50).convert("RGB").save(b, "JPEG")

        class Arq(io.BytesIO):
            name = "f.jpg"; type = "image/jpeg"; size = 0
        sb = banco(); sb.falhar_em.add("coletas")
        ST.respostas.update({"foto_0": Arq(b.getvalue()), "Enviar para aprovação": True})
        from ui.coletor import enviar
        enviar.render(sb)
        primeira = dict(ST.session_state["tentativa_envio_0"])
        enviar.render(sb)
        self.assertEqual(ST.session_state["tentativa_envio_0"], primeira)
        self.assertEqual(len(sb.arquivos), 2)  # foto + miniatura, sobrescritas (não 4)


class TestDivisaoAtomica(unittest.TestCase):
    def test_usa_rpc_quando_existe(self):
        from core import divisao

        class Exec:
            def __init__(self, data): self.data = data
            def execute(self): return self

        class Sb(fakes.FakeSupabase):
            chamadas_rpc = []

            def rpc(self, nome, args):
                Sb.chamadas_rpc.append((nome, args))
                return Exec([{"novo_id": 7, "parte_dono": 105.0, "parte_parceiro": 105.0}] if nome == "dividir_coleta" else 1)
        sb = Sb(coletas=[{"id": 1, "data": "2026-10-10", "coletor": "Ana", "quantidade": 21, "foto_url": "x", "status": "Aprovado",
                          "valor_total": 210.0, "pago": False, "divisao_de": None, "dividida_com": None}])
        self.assertEqual(divisao.dividir(sb, 1, "Bia"), (7, 105.0, 105.0))
        self.assertEqual(Sb.chamadas_rpc[0], ("dividir_coleta", {"p_id": 1, "p_parceiro": "Bia"}))
        self.assertEqual(len(sb.tabelas["coletas"]), 1)  # nada gravado pelo caminho antigo

    def test_erro_do_banco_vira_mensagem_e_funcao_ausente_cai_no_jeito_antigo(self):
        from core import divisao

        class Exec:
            def __init__(self, erro): self.erro = erro
            def execute(self): raise self.erro

        class Sb(fakes.FakeSupabase):
            erro = None

            def rpc(self, nome, args):
                return Exec(Sb.erro)
        linha = {"id": 1, "data": "2026-10-10", "coletor": "Ana", "quantidade": 21, "foto_url": "x", "status": "Aprovado",
                 "valor_total": 210.0, "pago": False, "divisao_de": None, "dividida_com": None}
        sb = Sb(coletas=[dict(linha)])
        Sb.erro = RuntimeError("Coleta #1: já foi dividida.")
        with self.assertRaises(divisao.ErroDivisao) as e:
            divisao.dividir(sb, 1, "Bia")
        self.assertIn("já foi dividida", str(e.exception))
        Sb.erro = RuntimeError("Could not find the function public.dividir_coleta")
        novo, dono, parc = divisao.dividir(sb, 1, "Bia")
        self.assertEqual((dono, parc), (105.0, 105.0))
        self.assertEqual(len(sb.tabelas["coletas"]), 2)


class TestPlanoB(unittest.TestCase):
    def setUp(self):
        ST.session_state.clear(); ST.respostas.clear(); ST.avisos.clear()

    def test_cookies_que_falham_nao_impedem_nada(self):
        from core import sessao

        class Quebrado:
            def get(self, n): raise TypeError("argument of type 'NoneType' is not a container or iterable")
            def set(self, *a, **k): raise TypeError("x")
            def remove(self, n): raise TypeError("x")
        c = sessao.CookiesSeguros(Quebrado())
        self.assertIsNone(c.get("a")); c.set("a", "b"); c.remove("a")
        sessao.CookiesSeguros(None).set("a", "b")

    def test_plano_b_mostra_o_login_quando_a_abertura_falha(self):
        from ui import falhas
        chamadas = []
        falhas.rodar_protegido(lambda: (_ for _ in ()).throw(TypeError("x")), obter_sb=lambda: object(),
                               plano_b=lambda obter: chamadas.append(obter()))
        self.assertEqual(len(chamadas), 1)

    def test_plano_b_quebrado_nao_derruba(self):
        from ui import falhas
        falhas.rodar_protegido(lambda: (_ for _ in ()).throw(TypeError("x")), plano_b=lambda obter: 1 / 0)
        self.assertTrue(ST.avisos)

    def test_local_do_erro_aparece_na_auditoria(self):
        from ui import falhas
        sb = fakes.FakeSupabase(auditoria=[])

        def quebra():
            None in None  # noqa: B015
        falhas.rodar_protegido(quebra, obter_sb=lambda: sb)
        detalhe = sb.tabelas["auditoria"][0]["detalhe"]
        self.assertIn("TypeError", detalhe)
        self.assertIn("test_robustez.py", detalhe)
