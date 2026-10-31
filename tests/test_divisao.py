"""Divisão de coleta entre dois coletores (50/50): valores, totais contados uma vez, bloqueios e desfazer."""
import unittest

from tests import fakes

fakes.instalar()


def banco(**extra):
    base = {"id": 1, "data": "2026-10-10", "coletor": "Ana", "quantidade": 21, "foto_url": "x.jpg", "status": "Aprovado",
            "valor_total": 210.0, "pago": False, "qtd_acrescimo": 0, "divisao_de": None, "dividida_com": None}
    base.update(extra)
    return fakes.FakeSupabase(coletas=[base])


class TestDivisao(unittest.TestCase):
    def test_partes_em_centavos(self):
        from core import divisao
        self.assertEqual(divisao.partes(210), (105.0, 105.0))
        self.assertEqual(divisao.partes(0.01), (0.01, 0.0))
        d, p = divisao.partes(100.01)  # centavo que sobra fica com o dono
        self.assertEqual((d, p), (50.01, 50.0))
        self.assertAlmostEqual(d + p, 100.01)

    def test_dividir_cria_parte_do_parceiro_e_reduz_a_do_dono(self):
        from core import divisao
        sb = banco()
        novo, dono, parc = divisao.dividir(sb, 1, "Bia")
        linhas = {r["id"]: r for r in sb.tabelas["coletas"]}
        self.assertEqual((dono, parc), (105.0, 105.0))
        self.assertEqual(linhas[1]["valor_total"], 105.0)
        self.assertEqual(linhas[1]["dividida_com"], "Bia")
        f = linhas[novo]
        self.assertEqual((f["coletor"], f["quantidade"], f["valor_total"], f["divisao_de"], f["dividida_com"], f["status"]),
                         ("Bia", 21, 105.0, 1, "Ana", "Aprovado"))

    def test_aparelhos_contam_uma_vez_nos_totais_e_cada_um_recebe_sua_parte(self):
        from core import divisao
        from core import financeiro as fin
        sb = banco()
        divisao.dividir(sb, 1, "Bia")
        c = fin.df_coletas(sb.tabelas["coletas"])
        self.assertEqual(len(fin.sem_duplicadas(c)), 1)
        f = fin.calcular_fechamento(c, fin.df_vales([]), fin.df_premios([]))
        self.assertEqual(f.aparelhos, 21)
        self.assertAlmostEqual(f.reais("nao_pago"), 210.0)
        for nome in ("Ana", "Bia"):
            fc = fin.calcular_fechamento(c[c["coletor"] == nome], fin.df_vales([]), fin.df_premios([]))
            self.assertEqual(fc.aparelhos, 21)
            self.assertAlmostEqual(fc.reais("nao_pago"), 105.0)

    def test_bloqueios(self):
        from core import divisao
        for extra, trecho in [({"status": "Pendente"}, "aprovada"), ({"pago": True}, "paga"),
                              ({"dividida_com": "Caio"}, "dividida")]:
            sb = banco(**extra)
            with self.assertRaises(divisao.ErroDivisao) as e:
                divisao.dividir(sb, 1, "Bia")
            self.assertIn(trecho, str(e.exception))
            self.assertEqual(len(sb.tabelas["coletas"]), 1)
        with self.assertRaises(divisao.ErroDivisao):
            divisao.dividir(banco(), 1, "Ana")
        with self.assertRaises(divisao.ErroDivisao):
            divisao.dividir(banco(), 1, "")

    def test_desfazer_devolve_o_valor(self):
        from core import divisao
        sb = banco()
        novo, _, _ = divisao.dividir(sb, 1, "Bia")
        self.assertEqual(divisao.desfazer(sb, novo), 1)
        self.assertEqual(len(sb.tabelas["coletas"]), 1)
        r = sb.tabelas["coletas"][0]
        self.assertEqual((r["valor_total"], r["dividida_com"]), (210.0, None))

    def test_desfazer_bloqueado_se_paga(self):
        from core import divisao
        sb = banco()
        novo, _, _ = divisao.dividir(sb, 1, "Bia")
        for r in sb.tabelas["coletas"]:
            if r["id"] == novo:
                r["pago"] = True
        with self.assertRaises(divisao.ErroDivisao):
            divisao.desfazer(sb, novo)
        self.assertEqual(len(sb.tabelas["coletas"]), 2)


if __name__ == "__main__":
    unittest.main()
