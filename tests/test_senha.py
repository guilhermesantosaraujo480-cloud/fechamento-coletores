"""Esqueci a senha (pedido ao administrador), senha temporária, troca obrigatória e senha mínima de 8."""
import unittest

from tests import fakes

fakes.instalar()


def banco():
    from core import auth
    h = auth.gerar_hash_senha("antiga123")
    return fakes.FakeSupabase(
        usuarios=[{"id": 1, "usuario": "adm", "senha": h, "nome_completo": "Chefe", "cargo": "ADM"},
                  {"id": 2, "usuario": "ana", "senha": h, "nome_completo": "Ana", "cargo": "COLETOR"},
                  {"id": 3, "usuario": "off", "senha": h, "nome_completo": "Off", "cargo": "COLETOR", "ativo": False}],
        pedidos_senha=[])


class TestEsqueciASenha(unittest.TestCase):
    def test_senha_minima_8(self):
        from core import auth
        self.assertIsNotNone(auth.validar_senha_nova("1234567"))
        self.assertIsNone(auth.validar_senha_nova("12345678"))

    def test_pedido_so_para_usuario_ativo_e_sem_duplicar(self):
        from core import auth
        sb = banco()
        for login in ("ana", "ANA ", "ana", "naoexiste", "off", "", "x" * 100):
            auth.pedir_redefinicao(sb, login)  # nunca levanta erro nem revela se existe
        self.assertEqual([p["usuario"] for p in sb.tabelas["pedidos_senha"]], ["ana"])

    def test_limite_de_pedidos_abertos(self):
        from core import auth
        sb = banco()
        sb.tabelas["pedidos_senha"] = [{"id": i, "usuario": f"u{i}", "atendido": False} for i in range(auth.MAX_PEDIDOS_ABERTOS + 1)]
        auth.pedir_redefinicao(sb, "ana")
        self.assertEqual(len(sb.tabelas["pedidos_senha"]), auth.MAX_PEDIDOS_ABERTOS + 1)

    def test_atender_gera_temporaria_exige_troca_e_derruba_sessao(self):
        from core import auth
        sb = banco()
        sb.tabelas["usuarios"][1]["session_token"] = "xyz"
        auth.pedir_redefinicao(sb, "ana")
        pedido = auth.pedidos_abertos(sb)[0]
        self.assertEqual(pedido["nome_completo"], "Ana")
        temp = auth.atender_pedido(sb, pedido, "adm")
        self.assertGreaterEqual(len(temp), 10)
        ana = sb.tabelas["usuarios"][1]
        self.assertTrue(ana["trocar_senha"])
        self.assertIsNone(ana["session_token"])
        self.assertTrue(auth.conferir_senha(temp, ana["senha"])[0])
        self.assertFalse(auth.conferir_senha("antiga123", ana["senha"])[0])
        self.assertEqual(auth.pedidos_abertos(sb), [])
        r = auth.autenticar(sb, "ana", temp, auth.Limitador())
        self.assertTrue(r.ok)
        self.assertTrue(r.usuario["trocar_senha"])

    def test_troca_obrigatoria(self):
        from core import auth
        sb = banco()
        auth.pedir_redefinicao(sb, "ana")
        temp = auth.atender_pedido(sb, auth.pedidos_abertos(sb)[0], "adm")
        self.assertFalse(auth.concluir_troca_obrigatoria(sb, 2, "curta")[0])
        self.assertFalse(auth.concluir_troca_obrigatoria(sb, 2, temp)[0])  # igual à temporária
        ok, _ = auth.concluir_troca_obrigatoria(sb, 2, "minhaNova99")
        self.assertTrue(ok)
        ana = sb.tabelas["usuarios"][1]
        self.assertFalse(ana["trocar_senha"])
        self.assertTrue(auth.conferir_senha("minhaNova99", ana["senha"])[0])

    def test_ignorar_pedido(self):
        from core import auth
        sb = banco()
        auth.pedir_redefinicao(sb, "ana")
        auth.ignorar_pedido(sb, auth.pedidos_abertos(sb)[0], "adm")
        self.assertEqual(auth.pedidos_abertos(sb), [])
        self.assertFalse(sb.tabelas["usuarios"][1].get("trocar_senha"))

    def test_redefinicao_pelo_admin_tambem_exige_troca(self):
        from core import auth
        sb = banco()
        auth.definir_senha(sb, 2, "definidaPeloAdm1", exigir_troca=True)
        self.assertTrue(sb.tabelas["usuarios"][1]["trocar_senha"])

    def test_tela_de_login_resposta_igual_e_limite_por_sessao(self):
        from ui import login
        ST = fakes.instalar()
        ST.session_state.clear(); ST.respostas.clear(); ST.avisos.clear()
        sb = banco()
        for _ in range(4):
            ST.respostas.update({"Pedir nova senha": True, "esqueci_usuario": "naoexiste"})
            login._esqueci(sb)
        sucessos = [a for a in ST.avisos if a[0] == "success"]
        self.assertEqual(len(sucessos), login.MAX_PEDIDOS_POR_SESSAO)
        self.assertTrue(any(a[0] == "warning" for a in ST.avisos))
        self.assertEqual(sb.tabelas["pedidos_senha"], [])


if __name__ == "__main__":
    unittest.main()
