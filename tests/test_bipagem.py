"""Bipagem: extração do PDF, regra do ponto, fila, motor (com plataforma falsa) e o navegador (com Selenium falso)."""
import importlib
import os
import sys
import tempfile
import types
import unittest
from io import BytesIO

from tests import fakes

ST = fakes.instalar()

from bipagem import agente, extracao, fila, motor, regras  # noqa: E402


# ------------------------------------------------------------------------------ extração
PAGINA = "OS {os}\nCLIENTE X\n5518996932743\n{serial}\n"


class TestExtracao(unittest.TestCase):
    def test_serial_por_pagina_e_regra_de_letras(self):
        self.assertEqual(extracao.seriais_do_texto("tel 551899693274 serial E8458BD51201 e 123456789012"), ["E8458BD51201"])
        self.assertEqual(extracao.seriais_do_texto(""), [])
        self.assertEqual(extracao.seriais_do_texto("E8458BD51201 E8458BD51201"), ["E8458BD51201"])  # sem repetir na página

    def test_os_com_um_ou_dois_hifens(self):
        self.assertEqual(extracao.os_do_texto("OS 7942892103-NX"), "7942892103-NX")
        self.assertEqual(extracao.os_do_texto("OS 8-A8B08DD6F86-1"), "8-A8B08DD6F86-1")
        self.assertEqual(extracao.os_do_texto("DADOS GERAIS DA OS RETIRADOS"), "")

    def test_resumo_aponta_pagina_sem_serial_e_repetido(self):
        paginas = [PAGINA.format(os="1-NX", serial="E8458BD51201"), PAGINA.format(os="2-NX", serial=""),
                   PAGINA.format(os="3-NX", serial="E8458BD51201"), PAGINA.format(os="4-NX", serial="900A62B86CE1")]
        reg = extracao.extrair_paginas_texto(paginas)
        r = extracao.resumir(reg)
        self.assertEqual((r["paginas"], r["seriais"]), (4, 2))
        self.assertEqual([x["os"] for x in r["sem_serial"]], ["2-NX"])
        self.assertEqual(r["repetidos"], {"E8458BD51201": ["1-NX", "3-NX"]})
        self.assertEqual(extracao.seriais_unicos(reg), ["E8458BD51201", "900A62B86CE1"])

    def test_pdf_de_verdade(self):
        from reportlab.pdfgen import canvas
        buf = BytesIO()
        c = canvas.Canvas(buf)
        for os_, serial in (("111-NX", "E8458BD51201"), ("222-NX", "900A62B86CE1")):
            c.drawString(50, 750, f"OS {os_}")
            c.drawString(50, 700, serial)
            c.showPage()
        c.save()
        chamadas = []
        reg = extracao.extrair_pdf(BytesIO(buf.getvalue()), lambda p, t: chamadas.append((p, t)))
        self.assertEqual([(r["pagina"], r["os"], r["serial"]) for r in reg],
                         [(1, "111-NX", "E8458BD51201"), (2, "222-NX", "900A62B86CE1")])
        self.assertEqual(chamadas[-1], (2, 2))

    def test_planilha_coluna_numero(self):
        import pandas as pd
        buf = BytesIO()
        pd.DataFrame({"Numero": ["AAA", None, " BBB "]}).to_excel(buf, index=False)
        self.assertEqual(extracao.ler_planilha(BytesIO(buf.getvalue())), ["AAA", "BBB"])


# --------------------------------------------------------------------------------- regras
class TestRegras(unittest.TestCase):
    def test_lista_em_ordem_e_depois_com_ponto(self):
        s = ["A", "B", "C"]
        self.assertEqual([regras.candidato(s, i) for i in range(7)], ["A", "B", "C", "A.", "B.", "C.", "A.."])

    def test_pool_so_avanca_ao_consumir(self):
        p = regras.Pool(["A", "B"])
        self.assertEqual((p.atual(), p.atual()), ("A", "A"))
        p.consumir()
        self.assertEqual(p.atual(), "B")
        self.assertEqual(regras.Pool(["A", "B"], 2).atual(), "A.")
        with self.assertRaises(ValueError):
            regras.Pool([])

    def test_pontos_e_equipamentos(self):
        self.assertEqual((regras.pontos("AB"), regras.pontos("AB.."), regras.mais_um_ponto("AB.")), (0, 2, "AB.."))
        self.assertEqual(regras.codigo_do_equipamento("002 HGU"), "002")
        self.assertEqual(regras.codigo_do_equipamento("999 NOVO"), "999 NOVO")


# ----------------------------------------------------------------------------------- fila
class TestFila(unittest.TestCase):
    def test_ciclo_completo(self):
        sb = fakes.FakeSupabase()
        l = fila.criar_lote(sb, "adm", "Lote", ["A", "B"], 2, "002 HGU", "001 IPTV", 5)
        self.assertEqual((l["status"], l["equip2"], l["indice_pool"]), ("pendente", "001 IPTV", 0))
        self.assertEqual(fila.proximo_lote(sb)["id"], l["id"])
        fila.iniciar(sb, l, "pc")
        self.assertEqual(fila.obter_lote(sb, l["id"])["status"], "executando")
        fila.progresso(sb, l["id"], ordens_ok=2, indice_pool=4)
        fila.registrar_item(sb, l["id"], "1-NX", "ok", "A", "B", 1)
        self.assertEqual(len(fila.itens(sb, l["id"])), 1)
        self.assertFalse(fila.deve_parar(sb, l["id"]))
        fila.pedir_parada(sb, l["id"])
        self.assertTrue(fila.deve_parar(sb, l["id"]))
        self.assertEqual(fila.obter_lote(sb, l["id"])["status"], "parando")
        fila.finalizar(sb, l["id"], "parado", "x")
        fila.retomar(sb, l["id"])
        self.assertEqual(fila.obter_lote(sb, l["id"])["status"], "pendente")
        self.assertFalse(fila.deve_parar(sb, l["id"]))

    def test_cancelar_pendente_e_validacoes(self):
        sb = fakes.FakeSupabase()
        l = fila.criar_lote(sb, "adm", "", ["A"], 1, "002 HGU", "ignorado", 1)
        self.assertIsNone(l["equip2"])
        fila.pedir_parada(sb, l["id"])
        self.assertEqual(fila.obter_lote(sb, l["id"])["status"], "cancelado")
        self.assertIsNone(fila.proximo_lote(sb))
        for args in ((["A"], 3, "x", "y", 1), ([], 1, "x", "y", 1), (["A"], 1, "x", "y", 0)):
            with self.assertRaises(ValueError):
                fila.criar_lote(sb, "adm", "n", *args)

    def test_agente_online(self):
        sb = fakes.FakeSupabase()
        self.assertFalse(fila.agente_online(sb)[0])
        fila.sinal(sb, info="oi")
        self.assertEqual(fila.agente_online(sb)[:2], (True, "oi"))
        sb.tabelas["bipagem_agente"][0]["ultimo_sinal"] = "2020-01-01T00:00:00+00:00"
        self.assertFalse(fila.agente_online(sb)[0])

    def test_executando_tem_prioridade_na_retomada(self):
        sb = fakes.FakeSupabase()
        a = fila.criar_lote(sb, "adm", "a", ["A"], 1, "002 HGU", None, 1)
        b = fila.criar_lote(sb, "adm", "b", ["A"], 1, "002 HGU", None, 1)
        fila.iniciar(sb, b, "pc")
        self.assertEqual(fila.proximo_lote(sb)["id"], b["id"])
        self.assertNotEqual(a["id"], b["id"])


# ---------------------------------------------------------------------------------- motor
class PlataformaFalsa:
    def __init__(self, oss, duplicados=(), sempre_duplicado=False, falhas=None, permanece=()):
        self.lista, self.duplicados, self.sempre = list(oss), set(duplicados), sempre_duplicado
        self.falhas = dict(falhas or {})  # numero -> nome do método que falha (uma vez se int, sempre se "sempre")
        self.permanece, self.digitados, self.por_os, self.recuperou = set(permanece), [], {}, 0
        self.atual, self.ultimo_alerta, self.datas, self.fotos = None, "", [], []

    def _talvez_falhar(self, metodo):
        if self.falhas.get((self.atual, metodo)):
            if self.falhas[(self.atual, metodo)] != "sempre":
                self.falhas[(self.atual, metodo)] -= 1
            raise RuntimeError(f"{metodo} quebrou")

    def abrir_lista(self): pass
    def garantir_sessao(self): pass
    def listar_os(self): return list(self.lista)
    def aguardar_retorno_lista(self): pass
    def registrar_falha(self, numero, msg): self.fotos.append(numero)

    def recuperar(self):
        self.recuperou += 1

    def abrir_os(self, n):
        self.atual = n
        self._talvez_falhar("abrir_os")

    def iniciar_retirada(self): self._talvez_falhar("iniciar_retirada")
    def selecionar_equipamento(self, c): self.equip = c

    def tentar_serial(self, s, forte=False):
        self.digitados.append(s)
        self.por_os.setdefault(self.atual, []).append((self.equip, s))
        if self.sempre or s in self.duplicados:
            self.ultimo_alerta = "Número de série já existe"
            return "duplicado"
        return "ok"

    def salvar_perifericos(self): self._talvez_falhar("salvar_perifericos")

    def finalizar(self, data):
        self._talvez_falhar("finalizar")
        self.datas.append(data)
        if self.atual not in self.permanece:
            self.lista.remove(self.atual)


class ApiFalsa:
    def __init__(self, parar_na_chamada=None):
        self.itens, self.prog, self.sinais, self.chamadas, self.parar_na = [], [], 0, 0, parar_na_chamada

    def deve_parar(self):
        self.chamadas += 1
        return self.parar_na is not None and self.chamadas >= self.parar_na

    def progresso(self, **c): self.prog.append(c)
    def item(self, **c): self.itens.append(c)
    def sinal(self, info=""): self.sinais += 1


def lote(seriais, ordens, qtd=1, indice=0, e1="002 HGU", e2="001 IPTV"):
    return {"id": 1, "seriais": seriais, "qtd_aparelhos": qtd, "equip1": e1, "equip2": e2 if qtd == 2 else None,
            "limite_ordens": ordens, "indice_pool": indice, "ordens_ok": 0, "ordens_erro": 0}


def rodar(plat, l, api=None, **k):
    api = api or ApiFalsa()
    saida = motor.executar(l, plat, api, log=lambda *a: None, hoje=lambda: "17/10/2026", **k)
    return saida, api


class TestMotor(unittest.TestCase):
    def test_seriais_em_ordem_um_aparelho(self):
        p = PlataformaFalsa(["O1", "O2", "O3"])
        (st, msg), api = rodar(p, lote(["A", "B", "C"], 3))
        self.assertEqual(st, "concluido")
        self.assertEqual([i["serial1"] for i in api.itens], ["A", "B", "C"])
        self.assertTrue(all(i["status"] == "ok" for i in api.itens))
        self.assertEqual(p.datas, ["17/10/2026"] * 3)
        self.assertEqual(api.prog[-1]["indice_pool"], 3)
        self.assertEqual(p.por_os["O1"], [("002", "A")])

    def test_dois_aparelhos_por_os_com_tipos(self):
        p = PlataformaFalsa(["O1", "O2"])
        (st, _), api = rodar(p, lote(["A", "B", "C", "D"], 2, qtd=2))
        self.assertEqual(p.por_os["O1"], [("002", "A"), ("001", "B")])
        self.assertEqual(p.por_os["O2"], [("002", "C"), ("001", "D")])
        self.assertEqual((api.itens[0]["serial1"], api.itens[0]["serial2"]), ("A", "B"))

    def test_duplicado_ganha_ponto_e_depois_dois(self):
        p = PlataformaFalsa(["O1", "O2"], duplicados={"A", "A.", "B"})
        (st, _), api = rodar(p, lote(["A", "B"], 2))
        self.assertEqual(p.por_os["O1"], [("002", "A"), ("002", "A."), ("002", "A..")])
        self.assertEqual(p.por_os["O2"], [("002", "B"), ("002", "B.")])
        self.assertEqual([i["serial1"] for i in api.itens], ["A..", "B."])
        self.assertEqual(api.itens[0]["tentativas"], 3)
        self.assertIn("ponto", api.itens[0]["obs"])
        self.assertEqual(api.prog[-1]["indice_pool"], 2)  # cada OS gastou UM serial da lista

    def test_acaba_a_lista_e_recomeca_com_ponto(self):
        p = PlataformaFalsa(["O1", "O2", "O3", "O4", "O5"])
        rodar(p, lote(["A", "B", "C"], 5))
        self.assertEqual(p.digitados, ["A", "B", "C", "A.", "B."])

    def test_retoma_do_indice_salvo(self):
        p = PlataformaFalsa(["O1"])
        rodar(p, lote(["A", "B", "C"], 1, indice=2))
        self.assertEqual(p.digitados, ["C"])

    def test_respeita_o_limite_e_o_fim_da_lista(self):
        p = PlataformaFalsa(["O1", "O2", "O3"])
        (st, _), api = rodar(p, lote(["A", "B", "C"], 2))
        self.assertEqual(len(api.itens), 2)
        p2 = PlataformaFalsa(["O1"])
        (st, msg), _ = rodar(p2, lote(["A", "B"], 5))
        self.assertEqual(st, "concluido")
        self.assertIn("Não há mais OS", msg)

    def test_parar_a_pedido_nao_corta_no_meio_da_os(self):
        p = PlataformaFalsa(["O1", "O2", "O3"])
        (st, _), api = rodar(p, lote(["A", "B", "C"], 3), ApiFalsa(parar_na_chamada=2))
        self.assertEqual(st, "parado")
        self.assertEqual(len(api.itens), 1)  # a 1ª OS terminou inteira antes de parar

    def test_falha_antes_de_gravar_tenta_de_novo_e_nao_gasta_serial(self):
        p = PlataformaFalsa(["O1", "O2"], falhas={("O1", "iniciar_retirada"): 1})
        (st, _), api = rodar(p, lote(["A", "B"], 2))
        self.assertEqual([i["status"] for i in api.itens], ["ok", "ok"])
        self.assertEqual([i["serial1"] for i in api.itens], ["A", "B"])  # a falha não consumiu serial
        self.assertEqual(p.recuperou, 1)
        self.assertEqual(p.fotos, ["O1"])

    def test_falha_depois_de_gravar_nao_repete_e_pede_conferencia(self):
        p = PlataformaFalsa(["O1", "O2"], falhas={("O1", "finalizar"): "sempre"})
        (st, _), api = rodar(p, lote(["A", "B", "C"], 1))
        self.assertEqual(api.itens[0]["status"], "verificar")
        self.assertIn("CONFIRA", api.itens[0]["obs"])
        self.assertEqual(api.itens[1]["status"], "ok")  # seguiu para a próxima OS
        self.assertEqual(p.digitados.count("A"), 1)  # não bipou duas vezes a mesma OS
        self.assertEqual(p.por_os["O2"], [("002", "B")])

    def test_nunca_entra_em_loop_numa_os_travada(self):
        p = PlataformaFalsa(["O1", "O2", "O3", "O4", "O5"],
                            falhas={(o, "abrir_os"): "sempre" for o in ("O1", "O2", "O3", "O4", "O5")})
        (st, msg), api = rodar(p, lote(["A"], 10))
        self.assertEqual(st, "erro")
        self.assertIn("seguidas", msg)
        self.assertEqual(len(api.itens), 3)
        self.assertLess(p.recuperou, 10)

    def test_plataforma_recusa_sempre_vira_erro_com_o_texto_do_alerta(self):
        p = PlataformaFalsa(["O1"], sempre_duplicado=True)
        (st, _), api = rodar(p, lote(["A"], 1))
        self.assertEqual(api.itens[0]["status"], "erro")
        self.assertIn("já existe", api.itens[0]["obs"])
        self.assertLessEqual(max(regras.pontos(s) for s in p.digitados), regras.MAX_PONTOS)

    def test_os_que_continua_na_lista_nao_conta_como_feita(self):
        p = PlataformaFalsa(["O1", "O2"], permanece={"O1"})
        (st, _), api = rodar(p, lote(["A", "B"], 1))
        self.assertEqual(api.itens[0]["status"], "verificar")
        self.assertEqual(api.itens[1]["status"], "ok")

    def test_erro_ao_voltar_para_a_lista_encerra_com_mensagem(self):
        p = PlataformaFalsa(["O1"], falhas={("O1", "abrir_os"): "sempre"})
        p.recuperar = lambda: (_ for _ in ()).throw(RuntimeError("sem internet"))
        (st, msg), _ = rodar(p, lote(["A"], 1))
        self.assertEqual(st, "erro")
        self.assertIn("sem internet", msg)


# --------------------------------------------------------------------------------- agente
class TestAgente(unittest.TestCase):
    def setUp(self):
        self.antigo = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.antigo)
        self.tmp.cleanup()

    def env(self, **k):
        return {"SUPABASE_URL": "u", "SUPABASE_KEY": "k", "USUARIO": "x", "SENHA": "y", **k}

    def test_falta_configuracao(self):
        msgs = []
        self.assertEqual(agente.main({"SUPABASE_URL": "u"}, log=msgs.append), 2)
        self.assertIn("SENHA", msgs[0])

    def test_roda_um_lote_ate_o_fim_e_grava_tudo(self):
        sb = fakes.FakeSupabase()
        l = fila.criar_lote(sb, "adm", "Lote", ["A", "B"], 1, "002 HGU", None, 2)
        plat = PlataformaFalsa(["O1", "O2"])
        plat.entrar = lambda: None
        plat.fechar = lambda: None
        rc = agente.main(self.env(), criar_cliente=lambda u, k: sb, criar_plataforma=lambda env: plat,
                         dormir=lambda s: None, uma_vez=True, log=lambda *a: None)
        self.assertEqual(rc, 0)
        final = fila.obter_lote(sb, l["id"])
        self.assertEqual((final["status"], final["ordens_ok"], final["indice_pool"]), ("concluido", 2, 2))
        self.assertEqual([(i["os"], i["serial1"]) for i in fila.itens(sb, l["id"])], [("O1", "A"), ("O2", "B")])
        self.assertTrue(os.path.exists(os.path.join("bipagem_logs", f"lote_{l['id']}.csv")))
        self.assertTrue(fila.agente_online(sb)[0])

    def test_erro_ao_abrir_o_navegador_marca_o_lote_com_erro(self):
        sb = fakes.FakeSupabase()
        l = fila.criar_lote(sb, "adm", "Lote", ["A"], 1, "002 HGU", None, 1)

        def quebra(env):
            raise RuntimeError("chromedriver não encontrado")
        agente.main(self.env(), criar_cliente=lambda u, k: sb, criar_plataforma=quebra,
                    dormir=lambda s: None, uma_vez=True, log=lambda *a: None)
        final = fila.obter_lote(sb, l["id"])
        self.assertEqual(final["status"], "erro")
        self.assertIn("chromedriver", final["mensagem"])

    def test_queda_do_banco_nao_derruba_a_bipagem(self):
        sb = fakes.FakeSupabase()
        api = agente.ApiLote(sb, 1, log=lambda *a: None)
        sb.falhar_em.add("bipagem_lotes")
        api.progresso(ordens_ok=1)  # não explode
        self.assertFalse(api.deve_parar())
        api.item(os="O1", status="ok", serial1="A")  # grava o CSV mesmo com banco fora do ar
        self.assertTrue(os.path.exists(api.csv))


# -------------------------------------------------------------------- navegador (Selenium falso)
def selenium_falso():
    """Cria módulos `selenium.*` mínimos e um driver que simula a plataforma: alerta ao repetir serial."""
    class Timeout(Exception): pass
    class SemAlerta(Exception): pass

    class El:
        def __init__(self, driver, chave, texto=""):
            self.d, self.chave, self.text, self.valor, self.sel = driver, chave, texto, "", False

        def clear(self): self.valor = ""

        def click(self): self.d.cliques.append(self.chave)
        def send_keys(self, *teclas):
            for t in teclas:
                if t == "CTRL":
                    self.sel = True
                elif t == "BACKSPACE":
                    self.valor = "" if self.sel else self.valor[:-1]
                    self.sel = False
                elif t == "ENTER":
                    self.d.cliques.append("ENTER")
                else:
                    self.valor += t

    class Alerta:
        def __init__(self, d): self.d = d
        @property
        def text(self): return self.d.alerta
        def accept(self): self.d.alerta = None

    class Troca:
        def __init__(self, d): self.d = d
        @property
        def alert(self):
            if self.d.alerta is None:
                raise SemAlerta()
            return Alerta(self.d)
        @property
        def active_element(self): return self.d.ativo

    class Driver:
        def __init__(self, options=None):
            self.cliques, self.digitado, self.alerta, self.scripts, self.url = [], [], None, [], ""
            self.usados = set()
            self.els = {}
            self.login_visivel = False
            self.lista = ["O1", "O2"]
            self.ativo = El(self, "ativo")
            self.switch_to = Troca(self)
            self.opcoes = options

        def el(self, chave, texto=""):
            return self.els.setdefault(chave, El(self, chave, texto))

        def get(self, url): self.url = url

        def find(self, por, seletor):
            if seletor == "username" and not self.login_visivel:
                return None
            return self.el((por, seletor))

        def find_elements(self, por, seletor):
            if seletor == "username":
                return [self.el((por, seletor))] if self.login_visivel else []
            if "ajax-modal" in seletor:
                return [El(self, ("os", n), n) for n in self.lista]
            return [self.el((por, seletor))]

        def execute_script(self, js, *args):
            self.scripts.append((js, args))
            if "value" in js and len(args) == 2:
                args[0].valor = args[1]

        def save_screenshot(self, caminho):
            with open(caminho, "wb") as f:
                f.write(b"png")

        def quit(self): self.fechado = True

    class Espera:
        def __init__(self, driver, tempo): self.d, self.t = driver, tempo
        def until(self, cond):
            r = cond(self.d)
            if not r:
                raise Timeout()
            return r

    def pronto(chave):
        return lambda d: d.find(*chave)

    # o clique em "Adicionar" confere o serial digitado
    def instalar_comportamento(driver, duplicados):
        campo = driver.el(("id", "EquipamentosSerieOS"))
        adicionar = driver.el(("css selector", "a.adicionarEquipamento"))
        original = adicionar.click

        def clique():
            original()
            if campo.valor in duplicados:
                driver.alerta = "Número de série duplicado"
        adicionar.click = clique

    ec = types.SimpleNamespace(
        element_to_be_clickable=pronto, presence_of_element_located=pronto, visibility_of_element_located=pronto,
        alert_is_present=lambda: (lambda d: d.alerta is not None))
    sel = {}

    class Select:
        def __init__(self, el): self.el = el
        def select_by_visible_text(self, t): sel["status"] = t

    mods = {n: types.ModuleType(n) for n in (
        "selenium", "selenium.webdriver", "selenium.common", "selenium.common.exceptions", "selenium.webdriver.common",
        "selenium.webdriver.common.by", "selenium.webdriver.common.keys", "selenium.webdriver.support",
        "selenium.webdriver.support.expected_conditions", "selenium.webdriver.support.ui")}
    mods["selenium"].webdriver = mods["selenium.webdriver"]
    mods["selenium.webdriver"].Chrome = Driver
    mods["selenium.webdriver"].ChromeOptions = lambda: types.SimpleNamespace(add_argument=lambda a: None)
    mods["selenium.common.exceptions"].NoAlertPresentException = SemAlerta
    mods["selenium.common.exceptions"].TimeoutException = Timeout
    mods["selenium.webdriver.common.by"].By = types.SimpleNamespace(ID="id", XPATH="xpath", CSS_SELECTOR="css selector")
    mods["selenium.webdriver.common.keys"].Keys = types.SimpleNamespace(CONTROL="CTRL", BACKSPACE="BACKSPACE", ENTER="ENTER")
    mods["selenium.webdriver.support.expected_conditions"] = ec
    mods["selenium.webdriver.support.ui"].Select = Select
    mods["selenium.webdriver.support.ui"].WebDriverWait = Espera
    return mods, instalar_comportamento, sel


class TestReintegraComSeleniumFalso(unittest.TestCase):
    def setUp(self):
        mods, self.comportamento, self.sel = selenium_falso()
        self.salvos = {n: sys.modules.get(n) for n in list(mods) + ["bipagem.reintegra"]}
        sys.modules.pop("bipagem.reintegra", None)
        sys.modules.update({n: m for n, m in mods.items()})
        self.mod = importlib.import_module("bipagem.reintegra")
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        for n, m in self.salvos.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m
        self.tmp.cleanup()

    def plat(self, duplicados=()):
        p = self.mod.PlataformaReintegra("user", "senha", pausa=0, pasta_logs=self.tmp.name)
        self.comportamento(p.driver, set(duplicados))
        return p

    def test_login_e_filtro(self):
        p = self.plat()
        p.driver.login_visivel = True
        p.entrar()
        self.assertEqual(p.driver.url, self.mod.URL)
        self.assertEqual(p.driver.els[("id", "username")].valor, "user")
        self.assertEqual(p.driver.els[("id", "password")].valor, "senha")
        p.driver.login_visivel = False
        p.abrir_lista()
        self.assertEqual(self.sel["status"], "Coletado App")
        self.assertTrue(any("click" in js for js, _ in p.driver.scripts))

    def test_lista_e_abre_a_os_certa(self):
        p = self.plat()
        self.assertEqual(p.listar_os(), ["O1", "O2"])
        p.abrir_os("O2")
        with self.assertRaises(self.mod.ErroPlataforma):
            p.abrir_os("O9")

    def test_serial_ok_e_duplicado_com_limpeza_forte(self):
        p = self.plat(duplicados={"A"})
        p.selecionar_equipamento("002")
        self.assertIn("ENTER", p.driver.cliques)
        self.assertEqual(p.driver.ativo.valor, "002")
        self.assertEqual(p.tentar_serial("A", forte=False), "duplicado")
        self.assertIn("duplicado", p.ultimo_alerta)
        self.assertIsNone(p.driver.alerta)  # o alerta foi aceito
        self.assertEqual(p.tentar_serial("A.", forte=True), "ok")
        self.assertEqual(p.driver.els[("id", "EquipamentosSerieOS")].valor, "A.")  # limpou antes de digitar de novo

    def test_finalizar_preenche_data_e_confirma_alerta(self):
        p = self.plat()
        p.driver.alerta = "Confirma?"
        p.finalizar("17/10/2026")
        self.assertEqual(p.driver.els[("id", "DataColeta")].valor, "17/10/2026")
        self.assertIn(("id", "encerrarOS"), p.driver.cliques)
        self.assertIsNone(p.driver.alerta)

    def test_sessao_caida_entra_de_novo_e_recuperar_volta_para_a_lista(self):
        p = self.plat()
        p.driver.login_visivel = True
        p.garantir_sessao()
        self.assertEqual(p.driver.els[("id", "username")].valor, "user")
        p.driver.login_visivel = False
        p.driver.alerta = "x"
        p.recuperar()
        self.assertIsNone(p.driver.alerta)

    def test_foto_do_erro_e_pausa_zero(self):
        p = self.plat()
        p.registrar_falha("O1", "boom")
        import glob
        self.assertEqual(len(glob.glob(os.path.join(self.tmp.name, "erro_*_O1.png"))), 1)
        p.fechar()

    def test_motor_ponta_a_ponta_com_o_navegador_falso(self):
        p = self.plat(duplicados={"AAA"})
        p.driver.lista = ["O1"]
        orig = p.finalizar

        def finalizar(data):
            orig(data)
            p.driver.lista.remove("O1")
        p.finalizar = finalizar
        api = ApiFalsa()
        st, _ = motor.executar(lote(["AAA", "BBB"], 1), p, api, log=lambda *a: None, hoje=lambda: "17/10/2026")
        self.assertEqual(st, "concluido")
        self.assertEqual((api.itens[0]["status"], api.itens[0]["serial1"]), ("ok", "AAA."))


class TestSemSelenium(unittest.TestCase):
    def test_site_importa_o_modulo_mesmo_sem_selenium(self):
        sys.modules.pop("bipagem.reintegra", None)
        antigos = {n: sys.modules.pop(n) for n in list(sys.modules) if n == "selenium" or n.startswith("selenium.")}
        try:
            mod = importlib.import_module("bipagem.reintegra")
            if mod.webdriver is None:
                with self.assertRaises(RuntimeError):
                    mod.PlataformaReintegra("u", "s")
        finally:
            sys.modules.update(antigos)
            sys.modules.pop("bipagem.reintegra", None)


if __name__ == "__main__":
    unittest.main()
