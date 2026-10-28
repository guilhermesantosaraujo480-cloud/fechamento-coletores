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


class TestJaEnviadosFiltrado(unittest.TestCase):
    def banco(self):
        linhas = [{"id": i, "protocolo": f"P{i}", "email": f"c{i}@x.com", "status": "enviado"} for i in range(1, 401)]
        linhas.append({"id": 999, "protocolo": "P1", "email": "c1@x.com", "status": "erro"})
        return fakes.FakeSupabase(envios_email=linhas)

    def test_filtrado_e_igual_ao_completo_para_os_protocolos_da_campanha(self):
        from disparador import repositorio as repo
        sb = self.banco()
        completo = repo.ja_enviados(sb)
        parcial = repo.ja_enviados(sb, [f"P{i}" for i in range(1, 301)] + ["P9999"])
        self.assertEqual(parcial, {c for c in completo if int(c.split("|")[0][1:]) <= 300})
        self.assertEqual(len(completo), 400)

    def test_protocolo_estranho_ou_vazio_le_o_historico_todo(self):
        from disparador import repositorio as repo
        sb = self.banco()
        self.assertEqual(len(repo.ja_enviados(sb, ["P1", ""])), 400)
        self.assertEqual(len(repo.ja_enviados(sb, ["P1", "a,b)"])), 400)
        self.assertEqual(len(repo.ja_enviados(sb, [])), 400)


class TestContatoQuemClicou(unittest.TestCase):
    def envios(self):
        return pd.DataFrame([
            {"envio_id": "e1", "protocolo": "100", "nome": "Maria Silva", "email": "maria@x.com", "modelo": "A", "status": "enviado"},
            {"envio_id": "e2", "protocolo": "200", "nome": "João", "email": "joao@x.com", "modelo": "B", "status": "enviado"},
            {"envio_id": "e3", "protocolo": "300", "nome": "Ana", "email": "ana@x.com", "modelo": "B", "status": "enviado"},
            {"envio_id": "e4", "protocolo": "400", "nome": "Rui", "email": "rui@x.com", "modelo": "B", "status": "enviado"},
        ])

    def cliques(self):
        return pd.DataFrame([
            {"envio_id": "e1", "perfil": "Pessoa", "data_hora": "2026-10-20T15:00:00+00:00"},
            {"envio_id": "e1", "perfil": "Pessoa", "data_hora": "2026-10-20T16:00:00+00:00"},
            {"envio_id": "e2", "perfil": "Pessoa", "data_hora": "2026-10-21T12:00:00+00:00"},
            {"envio_id": "e3", "perfil": "Pessoa", "data_hora": "2026-10-21T12:00:00+00:00"},
            {"envio_id": "e4", "perfil": "Robô", "data_hora": "2026-10-21T12:00:01+00:00"},
        ])

    def test_so_pessoas_um_por_email(self):
        from disparador import contato
        q = contato.quem_clicou(self.cliques(), self.envios())
        self.assertEqual(sorted(q["protocolo"]), ["100", "200", "300"])  # robô (400) fora; e1 uma linha só

    def test_links_descadastro_e_fixo(self):
        from disparador import contato
        q = contato.quem_clicou(self.cliques(), self.envios())
        fonte = {"100|maria@x.com": ("(11) 98765-4321", ""), "200|joao@x.com": ("1133334444", ""),
                 "300|ana@x.com": ("11912345678", "")}
        tabela, r = contato.montar_tabela(q, [fonte], {"ana@x.com"}, contato.MENSAGEM_PADRAO, "Minha Empresa")
        self.assertEqual(r, {"clicaram": 3, "com_whatsapp": 1, "sem_telefone": 1, "descadastrados": 1})
        maria = tabela[tabela["Protocolo"] == "100"].iloc[0]
        self.assertTrue(maria["WhatsApp"].startswith("https://wa.me/5511987654321?text="))
        self.assertIn("Maria", maria["WhatsApp"].replace("%20", " "))
        self.assertIn("100", maria["WhatsApp"])
        self.assertNotIn("Ana", " ".join(tabela["Cliente"]))        # quem saiu não aparece
        self.assertEqual(tabela[tabela["Protocolo"] == "200"].iloc[0]["WhatsApp"], "")  # fixo não tem WhatsApp
        self.assertEqual(list(tabela.columns), contato.COLUNAS_SAIDA)
        t2, _ = contato.montar_tabela(q, [fonte], {"ana@x.com"}, contato.MENSAGEM_PADRAO, "Minha Empresa", {"100|maria@x.com"})
        self.assertEqual(t2[t2["Protocolo"] == "100"].iloc[0]["Chamado"], "✅")
        self.assertEqual(t2[t2["Protocolo"] == "200"].iloc[0]["Chamado"], "")

    def test_telefone_vem_da_fila_e_da_planilha(self):
        from disparador import contato
        reg = {"protocolo": "100", "nome": "Maria", "email": "maria@x.com", "telefone": "11987654321"}
        base = {"endereco": "", "numero": "", "bairro": "", "cep": "", "tipo": "", "telefone2": ""}
        sb = fakes.FakeSupabase(contas_email=[])
        fila.criar_campanha(sb, "adm", "T", "M", {"tipo": "padrao1"}, CTX, 1, 1, False, [{**base, **reg}])
        self.assertEqual(contato.telefones_da_fila(sb, ["100", "999"]), {"100|maria@x.com": ("11987654321", "")})
        df = pd.DataFrame({"BA": [200, 300], "Cliente": ["J", "A"], "Email": ["joao@x.com", "ana@x.com"],
                           "Celular": [11999998888.0, "11 91234-5678"]})
        mapa = colunas.detectar_colunas(df)
        self.assertEqual(mapa["telefone"], "Celular")
        achados = contato.telefones_da_planilha(df, mapa)
        self.assertEqual(achados["200|joao@x.com"][0], "11999998888")
        self.assertEqual(achados["200|"][0], "11999998888")      # só pelo protocolo
        self.assertEqual(achados["|ana@x.com"][0], "11 91234-5678")  # só pelo e-mail

    def test_sem_cliques_ou_sem_envio(self):
        from disparador import contato
        self.assertTrue(contato.quem_clicou(pd.DataFrame(), self.envios()).empty)
        self.assertTrue(contato.quem_clicou(self.cliques(), pd.DataFrame()).empty)


class TestLigarCliquesAosEnvios(unittest.TestCase):
    """Clique gravado com identificador diferente do envio_id continua ligado ao e-mail certo."""

    def envios(self):
        return pd.DataFrame([
            {"id": 10, "envio_id": "uuid-aaa", "data_hora": "2026-10-20T12:00:00+00:00", "email": "ana@x.com", "protocolo": "111",
             "nome": "Ana", "modelo": "M1", "status": "enviado"},
            {"id": 11, "envio_id": "uuid-bbb", "data_hora": "2026-10-20T12:00:00+00:00", "email": "bia@x.com", "protocolo": "222",
             "nome": "Bia", "modelo": "M2", "status": "enviado"},
            {"id": 12, "envio_id": "uuid-ccc", "data_hora": "2026-10-20T12:00:00+00:00", "email": "caio@x.com", "protocolo": "333",
             "nome": "Caio", "modelo": "M2", "status": "enviado"},
        ])

    def test_liga_por_envio_id_id_protocolo_e_email(self):
        cliques = pd.DataFrame([
            {"id": 1, "envio_id": " UUID-AAA ", "data_hora": "2026-10-21T12:00:00+00:00"},                 # maiúscula/espaço
            {"id": 2, "envio_id": "11", "data_hora": "2026-10-21T12:00:00+00:00"},                          # id numérico do envio
            {"id": 3, "envio_id": None, "protocolo": "333", "data_hora": "2026-10-21T12:00:00+00:00"},      # só protocolo
            {"id": 4, "envio_id": "nada", "email": "ana@x.com", "data_hora": "2026-10-21T12:00:00+00:00"},  # só e-mail
            {"id": 5, "envio_id": "lixo", "data_hora": "2026-10-21T12:00:00+00:00"},                        # não liga
        ])
        df, d = metricas.ligar_aos_envios(cliques, self.envios())
        self.assertEqual(list(df["envio_id"][:4]), ["uuid-aaa", "uuid-bbb", "uuid-ccc", "uuid-aaa"])
        self.assertEqual(df["envio_id"].iloc[4], "lixo")  # nada some
        self.assertEqual(d["ligados"], 4)
        self.assertEqual(d["sem_ligacao"], 1)
        self.assertEqual(set(d["por_metodo"]), {"envio_id", "id do envio", "protocolo", "e-mail"})

    def test_desempenho_e_lista_funcionam_depois_da_ligacao(self):
        cliques = pd.DataFrame([{"id": 2, "envio_id": "11", "data_hora": "2026-10-22T12:00:00+00:00"}])
        df, _ = metricas.ligar_aos_envios(cliques, self.envios())
        c = metricas.classificar_cliques(df, self.envios())
        r = metricas.desempenho_por_modelo(self.envios(), c).set_index("Modelo")
        self.assertEqual(r.loc["M2", "Clicaram (pessoas)"], 1)
        from disparador import contato
        q = contato.quem_clicou(c, self.envios())
        self.assertEqual(list(q["protocolo"]), ["222"])

    def test_sem_dados_nao_quebra(self):
        d0, d = metricas.ligar_aos_envios(pd.DataFrame(), self.envios())
        self.assertTrue(d0.empty)
        df, d = metricas.ligar_aos_envios(pd.DataFrame([{"envio_id": "x"}]), pd.DataFrame())
        self.assertEqual(d["sem_ligacao"], 1)


class TestJaChamado(unittest.TestCase):
    def test_marcar_listar_desmarcar(self):
        from disparador import repositorio as repo
        sb = fakes.FakeSupabase()
        self.assertEqual(repo.marcar_chamados(sb, [("100", "Maria@X.com"), ("200", "j@x.com")], "adm"), 2)
        self.assertEqual(repo.chamados(sb), {"100|maria@x.com", "200|j@x.com"})
        repo.marcar_chamados(sb, [("100", "maria@x.com")], "adm")  # de novo: não duplica
        self.assertEqual(len(sb.tabelas["cliques_chamados"]), 2)
        repo.desmarcar_chamado(sb, "100", "MARIA@x.com")
        self.assertEqual(repo.chamados(sb), {"200|j@x.com"})

    def test_sem_a_tabela_nao_quebra(self):
        from disparador import repositorio as repo
        sb = fakes.FakeSupabase()
        sb.falhar_em = {"cliques_chamados"}
        self.assertEqual(repo.chamados(sb), set())
