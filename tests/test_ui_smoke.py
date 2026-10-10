"""Executa todas as páginas com Streamlit e banco falsos: pega NameError, KeyError, erros de pandas etc."""
import importlib
import unittest
from datetime import date

from tests import fakes

ST = fakes.instalar()


def banco(cheio=True):
    if not cheio:
        return fakes.FakeSupabase()
    from core import auth
    h = auth.gerar_hash_senha("segredo1")
    return fakes.FakeSupabase(
        usuarios=[{"id": 1, "usuario": "adm", "senha": h, "nome_completo": "Chefe", "cargo": "ADM"},
                  {"id": 2, "usuario": "ana", "senha": h, "nome_completo": "Ana", "cargo": "COLETOR"}],
        coletas=[{"id": 1, "data": "2026-10-02", "coletor": "Ana", "quantidade": 3, "foto_url": "a.jpg", "status": "Pendente", "valor_total": 30.0, "pago": False},
                 {"id": 2, "data": "2026-10-03", "coletor": "Ana", "quantidade": 2, "foto_url": None, "status": "Aprovado", "valor_total": 20.0, "pago": None}],
        vales_coleta=[{"id": 1, "data": "2026-10-04", "coletor": "Ana", "valor_vale": 5.0, "descricao": "x", "foto_url": "v.jpg"}],
        premiacoes=[{"id": 1, "data": "2026-10-04", "coletor": "Ana", "valor_premiacao": 7.5, "descricao": "meta"}],
        comprovantes_clientes=[{"id": 1, "cliente": "Maria", "ordem_servico": "123", "data_emissao": "2026-10-01", "arquivo_url": "https://x/y.pdf"}],
        logs_comprovantes=[{"id": 1, "usuario": "ana", "nome_completo": "Ana", "termo_pesquisado": "mar", "os_encontrada": "123", "data_hora": "2026-10-05T12:00:00+00:00"}],
        auditoria=[{"id": 1, "usuario": "adm", "acao": "x", "detalhe": "y", "data_hora": "2026-10-05T12:00:00+00:00"}],
        contas_email=[{"id": 1, "email": "c@g.com", "nome_remetente": "E", "limite_diario": 50, "ativa": True, "senha_app": "pura"}],
        envios_email=[{"id": 1, "envio_id": "e1", "protocolo": "1", "email": "a@b.com", "nome": "A", "conta": "c@g.com", "modelo": "m", "status": "enviado", "erro": "", "data_hora": "2026-10-05T12:00:00+00:00"}],
        cliques_email=[{"id": 1, "envio_id": "e1", "data_hora": "2026-10-05T13:00:00+00:00"}],
        modelos_email=[{"id": 1, "nome": "M", "assunto": "A", "texto": "T", "regras": "", "ativo": True}],
        descadastros=[{"email": "x@y.com", "motivo": "m", "data_hora": "2026-10-05T12:00:00+00:00"}],
    )


class Base(unittest.TestCase):
    def setUp(self):
        ST.session_state.clear()
        ST.respostas.clear()
        ST.avisos.clear()
        ST.secrets.clear()
        ST.secrets["EMPRESA_NOME"] = "Empresa Teste"
        ST.session_state["usuario"] = {"id": 1, "usuario": "adm", "nome_completo": "Chefe", "cargo": "ADM"}


class TestPaginasAdm(Base):
    def filtro(self):
        from ui.adm.filtros import Filtro
        return Filtro(date(2026, 10, 1), date(2026, 10, 31), "Todos")

    def test_paginas_com_dados_e_vazias(self):
        paginas = ["visao_geral", "coletas", "fechamento", "vales", "premiacoes"]
        for cheio in (True, False):
            for nome in paginas:
                m = importlib.import_module(f"ui.adm.{nome}")
                for coletor in ("Todos", "Ana"):
                    from ui.adm.filtros import Filtro
                    f = Filtro(date(2026, 10, 1), date(2026, 10, 31), coletor)
                    m.render(banco(cheio), f)
                    self.assertFalse([a for a in ST.avisos if a[0] == "error"], (nome, cheio, ST.avisos))
            for nome in ("usuarios", "auditoria", "emails"):
                importlib.import_module(f"ui.adm.{nome}").render(banco(cheio))
                self.assertFalse([a for a in ST.avisos if a[0] == "error"], (nome, cheio, ST.avisos))

    def test_todas_as_secoes_do_disparador(self):
        from disparador import ui
        for secao in ui.SECOES:
            ST.respostas["nav_email"] = secao
            ui.renderizar_disparador(banco())
            self.assertFalse([a for a in ST.avisos if a[0] == "error"], (secao, ST.avisos))

    def test_aprovar_coleta_grava_e_audita(self):
        from ui.adm import coletas
        db = banco()
        ST.respostas["ap_1"] = True
        with self.assertRaises(fakes.Reiniciar):
            coletas.render(db, self.filtro())
        self.assertEqual(db.tabelas["coletas"][0]["status"], "Aprovado")
        self.assertEqual(db.tabelas["auditoria"][-1]["acao"], "coleta_aprovado")

    def test_aprovar_nao_sobrescreve_decisao_de_outro_admin(self):
        from ui.adm import coletas
        db = banco()
        db.tabelas["coletas"][0]["status"] = "Recusado"
        ST.respostas["ap_1"] = True
        ST.respostas["nav_coletas"] = "⏳ Pendentes"
        coletas.render(db, self.filtro())  # não há mais pendentes: nada é exibido nem alterado
        self.assertEqual(db.tabelas["coletas"][0]["status"], "Recusado")

    def test_editor_salva_status_e_pago(self):
        from core import financeiro as fin
        from ui.adm import coletas
        db = banco()
        ST.respostas["nav_coletas"] = "📑 Lançamentos do período"
        original = fin.df_coletas(db.tabelas["coletas"]).set_index("id")[["data", "coletor", "quantidade", "valor_total", "status", "pago"]]
        editado = original.copy()
        editado["data"] = editado["data"].map(lambda d: d)
        editado.loc[2, "pago"] = True
        editado.loc[1, "status"] = "Recusado"
        editado.loc[1, "pago"] = True  # pago em coleta recusada deve ser ignorado
        ST.respostas["editor_coletas"] = editado
        ST.respostas["salvar_editor_coletas"] = True
        with self.assertRaises(fakes.Reiniciar):
            coletas.render(db, self.filtro())
        c1, c2 = db.tabelas["coletas"]
        self.assertEqual((c1["status"], c1["pago"]), ("Recusado", False))
        self.assertEqual((c2["status"], c2["pago"]), ("Aprovado", True))

    def test_lancar_premiacao_e_usuario_invalido(self):
        from ui.adm import premiacoes, usuarios
        db = banco()
        ST.respostas["Lançar premiação"] = True
        ST.respostas["Valor (R$)"] = 12.0
        with self.assertRaises(fakes.Reiniciar):
            premiacoes.render(db, self.filtro())
        self.assertEqual(db.tabelas["premiacoes"][-1]["valor_premiacao"], 12.0)
        ST.respostas.clear()
        ST.respostas.update({"Cadastrar": True, "Nome completo": "Zé", "Login de acesso": "Z E", "Senha (mínimo 6 caracteres)": "123456"})
        usuarios.render(db)
        self.assertTrue(any("Login inválido" in a[1] for a in ST.avisos))
        self.assertEqual(len(db.tabelas["usuarios"]), 2)


class TestColetorELogin(Base):
    def setUp(self):
        super().setUp()
        ST.session_state["usuario"] = {"id": 2, "usuario": "ana", "nome_completo": "Ana", "cargo": "COLETOR"}

    def test_paginas_do_coletor(self):
        from ui import conta
        from ui.coletor import comprovantes, enviar, extrato
        for cheio in (True, False):
            for secao in ("📱 Envios", "📉 Vales", "🏅 Premiações"):
                ST.respostas["nav_extrato"] = secao
                extrato.render(banco(cheio))
            enviar.render(banco(cheio))
            comprovantes.render(banco(cheio))
            conta.render(banco(cheio))
        self.assertFalse([a for a in ST.avisos if a[0] == "error"], ST.avisos)

    def test_busca_registra_log_uma_vez(self):
        from ui.coletor import comprovantes
        db = banco()
        ST.respostas["OS ou nome do cliente"] = "Mar"
        comprovantes.render(db)
        comprovantes.render(db)
        self.assertEqual(len(db.tabelas["logs_comprovantes"]), 2)  # 1 do seed + 1 nova (não 2 novas)
        ST.respostas["OS ou nome do cliente"] = "ab"
        comprovantes.render(db)
        self.assertTrue(any("3 caracteres" in a[1] for a in ST.avisos))

    def test_envio_de_coleta(self):
        from io import BytesIO
        from PIL import Image
        from ui.coletor import enviar
        buf = BytesIO()
        Image.new("RGB", (30, 30), "blue").save(buf, "JPEG")

        class Arq(BytesIO):
            pass
        db = banco()
        ST.respostas.update({"foto_0": Arq(buf.getvalue()), "qtd_0": 4, "Enviar para aprovação": True})
        with self.assertRaises(fakes.Reiniciar):
            enviar.render(db)
        nova = db.tabelas["coletas"][-1]
        self.assertEqual((nova["coletor"], nova["quantidade"], nova["status"], nova["valor_total"]), ("Ana", 4, "Pendente", 40.0))
        self.assertEqual(len(db.arquivos), 1)

    def test_fluxo_de_login_e_sessao(self):
        from core import sessao
        from ui import login
        ST.session_state.clear()
        db, cookies = banco(), sys_cookies()
        ST.respostas.update({"Entrar": True, "Usuário": "ana", "Senha": "segredo1"})
        with self.assertRaises(fakes.Reiniciar):
            login.render(db, cookies)
        self.assertEqual(ST.session_state["usuario"]["usuario"], "ana")
        token = cookies.get(sessao.COOKIE)
        ST.session_state.clear()
        sessao.restaurar(db, cookies)  # reabre pelo cookie
        self.assertEqual(ST.session_state["usuario"]["usuario"], "ana")
        db.tabelas["usuarios"][1]["ativo"] = False
        ST.session_state["_revalidado"] = 0
        with self.assertRaises(fakes.Reiniciar):
            sessao.revalidar(db, cookies)
        self.assertIsNone(token and cookies.get("outro"))


def sys_cookies():
    from streamlit_cookies_controller import CookieController
    return CookieController()


if __name__ == "__main__":
    unittest.main()


class TestApp(Base):
    def rodar_app(self, usuario):
        import runpy
        from core import db
        ST.secrets.update({"SUPABASE_URL": "u", "SUPABASE_KEY": "k"})
        banco_falso = banco()
        db._criar_cliente = lambda url, chave: banco_falso
        ST.session_state.clear()
        if usuario:
            ST.session_state["usuario"] = usuario
        runpy.run_path("app.py", run_name="__main__")

    def test_app_como_adm_percorre_todas_as_paginas(self):
        from tests.app_paginas import paginas_adm
        for pagina in paginas_adm():
            ST.respostas["nav_adm"] = pagina
            self.rodar_app({"id": 1, "usuario": "adm", "nome_completo": "Chefe", "cargo": "ADM"})
        self.assertFalse([a for a in ST.avisos if a[0] == "error"], ST.avisos)

    def test_app_como_coletor_e_deslogado(self):
        for pagina in ("📲 Enviar coleta", "📊 Meu extrato", "🔍 Comprovantes", "⚙️ Minha conta"):
            ST.respostas["nav_coletor"] = pagina
            self.rodar_app({"id": 2, "usuario": "ana", "nome_completo": "Ana", "cargo": "COLETOR"})
        self.rodar_app(None)  # tela de login
        self.assertFalse([a for a in ST.avisos if a[0] == "error"], ST.avisos)
