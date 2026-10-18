"""Edição de coletas, aparelhos acrescentados, saldo na Visão geral e a tela da bipagem."""
import unittest
from datetime import date
from io import BytesIO

from tests import fakes
from tests.test_ui_smoke import Base, banco

ST = fakes.instalar()


class Filtros:
    @staticmethod
    def periodo(coletor="Todos", ini=date(2026, 10, 1), fim=date(2026, 10, 31)):
        from ui.adm.filtros import Filtro
        return Filtro(ini, fim, coletor)


class TestAcrescimoFinanceiro(unittest.TestCase):
    def dados(self):
        from core import financeiro as fin
        return fin.df_coletas([
            {"id": 1, "data": "2026-10-17", "coletor": "Ana", "quantidade": 12, "status": "Aprovado", "valor_total": 120, "qtd_acrescimo": 2},
            {"id": 2, "data": "2026-10-05", "coletor": "Ana", "quantidade": 5, "status": "Aprovado", "valor_total": 50},
            {"id": 3, "data": "2026-10-17", "coletor": "Bia", "quantidade": 4, "status": "Pendente", "valor_total": 40, "qtd_acrescimo": 9},
        ])

    def test_so_conta_aprovadas_e_nao_mexe_no_fechamento(self):
        from core import financeiro as fin
        c = self.dados()
        self.assertEqual(fin.acrescimos(c), 2)
        f = fin.calcular_fechamento(c, fin.df_vales([]), fin.df_premios([]))
        self.assertEqual((f.aparelhos, f.bruto), (17, 17000))  # o acréscimo já está dentro: fechamento igual a antes
        resumo = fin.resumo_por_coletor(c, fin.df_vales([]), fin.df_premios([]))
        self.assertNotIn("Acrescentados", resumo.columns)

    def test_por_coletor_e_por_quinzena(self):
        from core import financeiro as fin
        c = self.dados()
        pc = fin.acrescimos_por_coletor(c)
        self.assertEqual((pc.iloc[0]["Coletor"], pc.iloc[0]["Acrescentados"], pc.iloc[0]["% do total"]), ("Ana", 2, 11.8))
        pq = fin.acrescimos_por_quinzena(c)
        self.assertEqual(list(pq["Quinzena"]), ["16/10 a 31/10/2026", "01/10 a 15/10/2026"])
        self.assertEqual(list(pq["Acrescentados"]), [2, 0])

    def test_sem_a_coluna_no_banco_tudo_zero(self):
        from core import financeiro as fin
        c = fin.df_coletas([{"id": 1, "data": "2026-10-17", "coletor": "Ana", "quantidade": 3, "status": "Aprovado", "valor_total": 30}])
        self.assertEqual(fin.acrescimos(c), 0)
        self.assertTrue(fin.acrescimos_por_coletor(c).empty)
        self.assertTrue(fin.acrescimos_por_coletor(fin.df_coletas([])).empty)


class TestEdicaoDeColeta(Base):
    def test_editar_pendente_com_acrescimo_grava_total_valor_e_audita(self):
        from ui.adm import coletas
        db = banco()
        ST.respostas.update({"ed_re_1": 5, "ed_ac_1": 2, "ed_vl_1_7": 70.0, "ed_sv_1": True})
        with self.assertRaises(fakes.Reiniciar):
            coletas.render(db, Filtros.periodo())
        c = db.tabelas["coletas"][0]
        self.assertEqual((c["quantidade"], c["qtd_acrescimo"], c["valor_total"], c["status"]), (7, 2, 70.0, "Pendente"))
        self.assertIn("acréscimo 0→2", db.tabelas["auditoria"][-1]["detalhe"])

    def test_sem_acrescimo_nao_toca_na_coluna_nova(self):
        from ui.adm import coletas
        db = banco()
        ST.respostas.update({"ed_re_1": 4, "ed_ac_1": 0, "ed_vl_1_4": 40.0, "ed_sv_1": True})
        with self.assertRaises(fakes.Reiniciar):
            coletas.render(db, Filtros.periodo())
        c = db.tabelas["coletas"][0]
        self.assertEqual((c["quantidade"], c["valor_total"]), (4, 40.0))
        self.assertNotIn("qtd_acrescimo", c)  # banco sem a migração continua funcionando

    def test_valor_sugerido_acompanha_a_quantidade(self):
        from ui.adm import coletas
        db = banco()
        ST.secrets["VALOR_POR_COLETA"] = "12"
        ST.respostas.update({"ed_re_1": 5, "ed_ac_1": 1, "ed_sv_1": True})  # total 6 x 12 = 72 (valor não informado: usa o sugerido)
        with self.assertRaises(fakes.Reiniciar):
            coletas.render(db, Filtros.periodo())
        self.assertEqual(db.tabelas["coletas"][0]["valor_total"], 72.0)

    def test_total_zero_e_recusado(self):
        from ui.adm import coletas
        db = banco()
        ST.respostas.update({"ed_re_1": 0, "ed_ac_1": 0, "ed_vl_1_0": 0.0, "ed_sv_1": True})
        coletas.render(db, Filtros.periodo())
        self.assertEqual(db.tabelas["coletas"][0]["quantidade"], 3)
        self.assertTrue(any("maior que zero" in a[1] for a in ST.avisos))

    def test_editar_pela_aba_de_lancamentos(self):
        from ui.adm import coletas
        db = banco()
        ST.respostas.update({"nav_coletas": "📑 Lançamentos do período", "ed_escolha": 2,
                             "edl_re_2": 2, "edl_ac_2": 1, "edl_vl_2_3": 30.0, "edl_sv_2": True})
        with self.assertRaises(fakes.Reiniciar):
            coletas.render(db, Filtros.periodo())
        c = db.tabelas["coletas"][1]
        self.assertEqual((c["quantidade"], c["qtd_acrescimo"], c["valor_total"]), (3, 1, 30.0))

    def test_erro_do_banco_mostra_dica_da_migracao(self):
        from ui.adm import coletas
        db = banco()
        original = db.table

        def tabela(nome):
            q = original(nome)
            if nome == "coletas":
                velho = q.update
                q.update = lambda payload: (_ for _ in ()).throw(RuntimeError("column qtd_acrescimo does not exist")) if "qtd_acrescimo" in payload else velho(payload)
            return q
        db.table = tabela
        ST.respostas.update({"ed_re_1": 5, "ed_ac_1": 2, "ed_vl_1_7": 70.0, "ed_sv_1": True})
        coletas.render(db, Filtros.periodo())
        self.assertTrue(any("migracao_v5" in a[1] for a in ST.avisos))


class TestVisaoGeral(Base):
    def test_saldo_negativo_da_quinzena_passada_aparece_no_ranking_e_no_aviso(self):
        from ui.adm import visao_geral
        db = banco()
        db.tabelas["coletas"] = [{"id": 9, "data": "2026-09-20", "coletor": "Ana", "quantidade": 1, "foto_url": None,
                                  "status": "Aprovado", "valor_total": 10.0, "pago": True}]
        db.tabelas["vales_coleta"] = [{"id": 9, "data": "2026-09-22", "coletor": "Ana", "valor_vale": 50.0, "descricao": "x", "foto_url": None}]
        db.tabelas["premiacoes"] = []
        visao_geral.render(db, Filtros.periodo(ini=date(2026, 10, 16), fim=date(2026, 10, 31)))
        erros = [a[1] for a in ST.avisos if a[0] == "error"]
        self.assertTrue(any("Ana" in e and "40,00" in e for e in erros), erros)

    def test_acrescimos_aparecem_na_visao_geral(self):
        from ui.adm import visao_geral
        db = banco()
        db.tabelas["coletas"][1]["qtd_acrescimo"] = 1
        ST.respostas["ver_acrescimos_quinzenas"] = True
        visao_geral.render(db, Filtros.periodo())
        self.assertFalse([a for a in ST.avisos if a[0] == "error"], ST.avisos)


class Arquivo:
    def __init__(self, nome, conteudo):
        self.name, self._c = nome, conteudo

    def getvalue(self):
        return self._c


class TestTelaBipagem(Base):
    def test_telas_vazias_e_sem_migracao_nao_quebram(self):
        from ui.adm import bipagem
        for cheio in (True, False):
            for secao in bipagem.SECOES:
                ST.respostas["nav_bipagem"] = secao
                bipagem.render(banco(cheio))
        self.assertFalse([a for a in ST.avisos if a[0] == "error"], ST.avisos)

    def test_enfileirar_a_partir_de_planilha(self):
        import pandas as pd
        from bipagem import fila
        from ui.adm import bipagem
        buf = BytesIO()
        pd.DataFrame({"Numero": ["AAA", "BBB", "CCC", "DDD"]}).to_excel(buf, index=False)
        db = banco()
        ST.respostas.update({"nav_bipagem": bipagem.SECOES[0], "bip_arquivo": Arquivo("Os.xlsx", buf.getvalue()),
                             "bip_qtd": 2, "bip_eq1": "002 HGU", "bip_eq2": "001 IPTV", "bip_confirma": True,
                             "bip_enfileirar": True})
        bipagem.render(db)
        lote = db.tabelas["bipagem_lotes"][0]
        self.assertEqual((lote["seriais"], lote["qtd_aparelhos"], lote["equip1"], lote["equip2"], lote["limite_ordens"]),
                         (["AAA", "BBB", "CCC", "DDD"], 2, "002 HGU", "001 IPTV", 2))
        self.assertEqual(db.tabelas["auditoria"][-1]["acao"], "bipagem_lote")
        self.assertEqual(fila.proximo_lote(db)["status"], "pendente")

    def test_sem_confirmar_nao_enfileira(self):
        import pandas as pd
        from ui.adm import bipagem
        buf = BytesIO()
        pd.DataFrame({"Numero": ["AAA"]}).to_excel(buf, index=False)
        db = banco()
        ST.respostas.update({"nav_bipagem": bipagem.SECOES[0], "bip_arquivo": Arquivo("Os.xlsx", buf.getvalue()),
                             "bip_enfileirar": True})
        bipagem.render(db)
        self.assertEqual(db.tabelas.get("bipagem_lotes", []), [])

    def test_pdf_mostra_resumo_e_enfileira_com_ordens_do_pdf(self):
        from reportlab.pdfgen import canvas
        from ui.adm import bipagem
        buf = BytesIO()
        c = canvas.Canvas(buf)
        for os_, serial in (("1-NX", "E8458BD51201"), ("2-NX", ""), ("3-NX", "900A62B86CE1")):
            c.drawString(50, 750, f"OS {os_}")
            if serial:
                c.drawString(50, 700, serial)
            c.showPage()
        c.save()
        db = banco()
        ST.respostas.update({"nav_bipagem": bipagem.SECOES[0], "bip_arquivo": Arquivo("os.pdf", buf.getvalue()),
                             "bip_confirma": True, "bip_enfileirar": True})
        bipagem.render(db)
        lote = db.tabelas["bipagem_lotes"][0]
        self.assertEqual((lote["seriais"], lote["limite_ordens"]), (["E8458BD51201", "900A62B86CE1"], 3))

    def test_lotes_com_botoes_de_parar_e_retomar(self):
        from bipagem import fila
        from ui.adm import bipagem
        db = banco()
        a = fila.criar_lote(db, "adm", "A", ["X"], 1, "002 HGU", None, 3)
        fila.iniciar(db, a, "pc")
        fila.registrar_item(db, a["id"], "1-NX", "ok", "X")
        ST.respostas.update({"nav_bipagem": bipagem.SECOES[1], f"bp_parar_{a['id']}": True})
        with self.assertRaises(fakes.Reiniciar):
            bipagem.render(db)
        self.assertEqual(fila.obter_lote(db, a["id"])["status"], "parando")
        fila.finalizar(db, a["id"], "parado", "x")
        ST.respostas.clear()
        ST.respostas.update({"nav_bipagem": bipagem.SECOES[1], f"bp_ret_{a['id']}": True})
        with self.assertRaises(fakes.Reiniciar):
            bipagem.render(db)
        self.assertEqual(fila.obter_lote(db, a["id"])["status"], "pendente")


class TestAppRegistraBipagem(Base):
    def test_pagina_esta_no_menu(self):
        import re
        with open("app.py", encoding="utf-8") as f:
            texto = f.read()
        self.assertTrue(re.search(r'"🔖 Bipagem": \(bipagem\.render, False\)', texto))


if __name__ == "__main__":
    unittest.main()
