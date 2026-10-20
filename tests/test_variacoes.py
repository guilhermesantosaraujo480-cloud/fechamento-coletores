"""Variação de modelos: sorteio balanceado, tom/layout, envio direto, fila em segundo plano e relatório por modelo."""
import unittest
from collections import Counter

import pandas as pd

from tests import fakes

fakes.instalar()

from disparador import campanha, colunas, fila, metricas, templates, variacoes, worker  # noqa: E402
from disparador.crypto import Cofre  # noqa: E402
from tests.test_fila import CONTA, CTX, Base, registros  # noqa: E402


def pacote_multi(pesos=None):
    modelos = list(variacoes.modelos_do_pacote().items())
    pesos = pesos or [1] * len(modelos)
    return variacoes.montar_multi([{"rotulo": n, "peso": p, "modelo": m} for (n, m), p in zip(modelos, pesos)])


class TestSorteio(unittest.TestCase):
    def test_pacote_tem_seis_modelos_com_tons_variados(self):
        pacote = variacoes.modelos_do_pacote()
        self.assertEqual(len(pacote), 6)
        self.assertEqual({m["tom"] for m in pacote.values()}, set(variacoes.TONS))
        self.assertEqual({m["layout"] for m in pacote.values()}, {"cartao", "simples"})

    def test_distribuicao_balanceada_para_2000(self):
        vs = variacoes.da_campanha(pacote_multi(), "x")
        cont = Counter(variacoes.atribuir(2000, vs, semente=1))
        self.assertEqual(sum(cont.values()), 2000)
        self.assertTrue(all(332 <= v <= 334 for v in cont.values()), cont)

    def test_pesos_respeitados_e_peso_zero_sai(self):
        multi = pacote_multi([2, 1, 1, 0, 0, 0])
        vs = variacoes.da_campanha(multi, "x")
        self.assertEqual(len(vs), 3)
        cont = Counter(variacoes.atribuir(400, vs))
        self.assertEqual((cont[0], cont[1], cont[2]), (200, 100, 100))

    def test_embaralhado_e_reproduzivel(self):
        vs = variacoes.da_campanha(pacote_multi(), "x")
        a, b = variacoes.atribuir(60, vs, semente=7), variacoes.atribuir(60, vs, semente=7)
        self.assertEqual(a, b)
        self.assertNotEqual(a, sorted(a))

    def test_limite_de_dez(self):
        m = {"tipo": "db", "assunto": "a", "texto": "b", "regras": ""}
        with self.assertRaises(ValueError):
            variacoes.montar_multi([{"rotulo": str(i), "peso": 1, "modelo": m} for i in range(11)])
        with self.assertRaises(ValueError):
            variacoes.montar_multi([])

    def test_indice_estranho_nao_quebra(self):
        self.assertEqual(variacoes.indice_da_linha([None], 0, 3), 0)
        self.assertEqual(variacoes.indice_da_linha([99], 0, 3), 0)
        self.assertEqual(variacoes.indice_da_linha([], 4, 3), 1)

    def test_modelo_simples_vira_uma_variante(self):
        vs = variacoes.da_campanha({"tipo": "padrao1"}, "Padrão")
        self.assertEqual([v["rotulo"] for v in vs], ["Padrão"])


class TestConteudo(unittest.TestCase):
    REG = {"nome": "Ana", "protocolo": "77", "email": "a@b.com", "endereco": "Rua A", "numero": "1", "bairro": "",
           "cep": "", "tipo": ""}

    def test_todos_os_modelos_do_pacote_renderizam_sem_inventar_multa(self):
        for nome, m in variacoes.modelos_do_pacote().items():
            d = templates.preparar_dados(self.REG, m, CTX, "e1")
            self.assertIn("77", d["assunto"], nome)
            self.assertIn("Ana", d["html"], nome)
            self.assertIn("SAIR", d["texto"], nome)
            self.assertNotIn("R$", d["html"], nome)
            self.assertNotIn("multa", d["html"].lower(), nome)

    def test_layout_simples_e_cartao_sao_diferentes(self):
        modelos = list(variacoes.modelos_do_pacote().values())
        simples = next(m for m in modelos if m["layout"] == "simples")
        cartao = next(m for m in modelos if m["layout"] == "cartao")
        self.assertNotIn("purple-card", templates.preparar_dados(self.REG, simples, CTX, "e")["html"])
        self.assertIn("purple-card", templates.preparar_dados(self.REG, cartao, CTX, "e")["html"])

    def test_assuntos_do_pacote_sao_todos_diferentes(self):
        assuntos = {templates.preparar_dados(self.REG, m, CTX, "e")["assunto"] for m in variacoes.modelos_do_pacote().values()}
        self.assertEqual(len(assuntos), 6)


class TestEnvioDireto(unittest.TestCase):
    def test_cada_pessoa_recebe_um_modelo_e_historico_guarda_o_rotulo(self):
        df = pd.DataFrame([{"protocolo": f"P{i}", "nome": f"C{i}", "email": f"c{i}@x.com"} for i in range(60)])
        mapa = {c: (c if c in df.columns else None) for c in colunas.CAMPOS}
        enviados, historico = [], []

        class Gerente:
            def enviar(self, conta, msg):
                enviados.append(msg["Subject"])

            def fechar_uma(self, email):
                pass

        params = campanha.Parametros(pacote_multi(), "🔀 Mistura", CTX, 1, 1)
        resumo = campanha.executar_campanha(
            df, mapa, [dict(CONTA, _senha="x", limite_diario=500)], {}, set(), set(), Gerente(), params,
            registrar=lambda eid, dados, conta, modelo, status, erro: historico.append(modelo) or True,
            dormir=lambda s: None, sortear=lambda a, b: a)
        self.assertEqual(resumo.sucessos, 60)
        import re
        self.assertEqual(len({re.sub(r'[PC]\d+', '', a) for a in enviados}), 6)  # seis assuntos diferentes saíram
        self.assertEqual(Counter(historico), Counter({n: 10 for n in variacoes.modelos_do_pacote()}))
        self.assertEqual({k: v["enviados"] for k, v in resumo.por_variante.items()},
                         {n: 10 for n in variacoes.modelos_do_pacote()})

    def test_modelo_unico_continua_igual(self):
        df = pd.DataFrame([{"protocolo": "P1", "nome": "C", "email": "c@x.com"}])
        mapa = {c: (c if c in df.columns else None) for c in colunas.CAMPOS}
        nomes = []

        class Gerente:
            def enviar(self, conta, msg):
                pass

            def fechar_uma(self, email):
                pass

        params = campanha.Parametros({"tipo": "padrao1"}, "Padrão 1", CTX, 1, 1)
        campanha.executar_campanha(df, mapa, [dict(CONTA, _senha="x", limite_diario=500)], {}, set(), set(), Gerente(), params,
                                   registrar=lambda e, d, c, modelo, s, er: nomes.append(modelo) or True,
                                   dormir=lambda s: None, sortear=lambda a, b: a)
        self.assertEqual(nomes, ["Padrão 1"])


class TestFilaMista(Base):
    def setUp(self):
        super().setUp()
        self.sb.tabelas["contas_email"][0]["limite_diario"] = 500

    def criar_multi(self, n=60):
        return fila.criar_campanha(self.sb, "adm", "Mista", "🔀 Mistura de 6 modelos", pacote_multi(), CTX, 5, 5, False,
                                   registros(n))

    def test_sorteio_guardado_na_fila_e_enviado_com_os_seis_modelos(self):
        c = self.criar_multi()
        ds = fila.destinos(self.sb, c["id"])
        self.assertEqual(Counter(d["dados"]["_variante"] for d in ds), Counter({i: 10 for i in range(6)}))
        self.rodar()
        self.assertEqual(self.status(c["id"]), "concluida")
        modelos = Counter(r["modelo"] for r in self.sb.tabelas["envios_email"])
        self.assertEqual(modelos, Counter({n: 10 for n in variacoes.modelos_do_pacote()}))

    def test_retomar_depois_de_pausa_mantem_o_modelo_de_cada_pessoa(self):
        c = self.criar_multi(12)
        antes = {d["email"]: d["dados"]["_variante"] for d in fila.destinos(self.sb, c["id"])}
        self.rodar(minutos=0.2)  # corta cedo
        self.rodar()
        rotulos = list(variacoes.modelos_do_pacote())
        for r in self.sb.tabelas["envios_email"]:
            self.assertEqual(r["modelo"], rotulos[antes[r["email"]]])

    def test_resumo_por_variante(self):
        c = self.criar_multi(12)
        self.rodar()
        vs = variacoes.da_campanha(fila.obter(self.sb, c["id"])["modelo"], "")
        tabela = fila.resumo_por_variante(fila.destinos(self.sb, c["id"]), vs)
        self.assertEqual(sum(t["Enviados"] for t in tabela), 12)
        self.assertTrue(all(t["Total"] == 2 for t in tabela))

    def test_campanha_antiga_de_um_modelo_nao_ganha_variante(self):
        c = self.criar()
        self.assertTrue(all("_variante" not in d["dados"] for d in fila.destinos(self.sb, c["id"])))


class TestRelatorioPorModelo(unittest.TestCase):
    def test_conta_por_modelo(self):
        envios = pd.DataFrame([
            {"envio_id": "1", "email": "a@x.com", "modelo": "A", "status": "enviado"},
            {"envio_id": "2", "email": "b@x.com", "modelo": "A", "status": "enviado"},
            {"envio_id": "3", "email": "c@x.com", "modelo": "B", "status": "enviado"},
            {"envio_id": "4", "email": "d@x.com", "modelo": "B", "status": "erro"},
        ])
        cliques = pd.DataFrame([{"envio_id": "1", "perfil": "Pessoa"}, {"envio_id": "3", "perfil": "Robô"}])
        r = metricas.desempenho_por_modelo(envios, cliques, {"b@x.com"}).set_index("Modelo")
        self.assertEqual((r.loc["A", "Enviados"], r.loc["A", "Clicaram (pessoas)"], r.loc["A", "Descadastros"]), (2, 1, 1))
        self.assertEqual((r.loc["B", "Enviados"], r.loc["B", "Erros"], r.loc["B", "Clicaram (pessoas)"]), (1, 1, 0))
        self.assertEqual(r.loc["A", "Taxa de clique"], "50.0%")

    def test_sem_dados(self):
        self.assertTrue(metricas.desempenho_por_modelo(pd.DataFrame(), pd.DataFrame()).empty)


if __name__ == "__main__":
    unittest.main()
