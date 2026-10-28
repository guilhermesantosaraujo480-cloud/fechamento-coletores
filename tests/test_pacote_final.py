"""Pacote final: Toolbox, cadastro de nova empresa (chave duplicada), mensagens do WhatsApp, fechamento por WhatsApp, SMS."""
import io
import unittest
from datetime import date

import pandas as pd

from tests import fakes
from tests.test_ui_smoke import Base, banco

from rotas import mensagens, processamento as pr, vinculos  # noqa: E402
from rotas import perfis as pf  # noqa: E402

ST = fakes.instalar()

COLUNAS_PEDIDOS = [
    "Número do Cliente", "Pedido", "Conta", "Status", "Tipo", "Origem - Nome", "Origem - Logradouro", "Origem - Número",
    "Origem - Bairro", "Origem - CEP", "Destino - Nome", "Destino - CPF/CNPJ", "Destino - Telefone", "Destino - Celular",
    "Destino - Logradouro", "Destino - Número", "Destino - Bairro", "Destino - Cidade", "Destino - CEP", "Destino - UF",
    "Destino - País", "Destino - Informação adicional", "Transportador", "Descrição dos itens"]


def pedidos():
    linhas = [
        ["1", "4001", "Rotalog", "Não Processado", "Entrega em Lote", "Orig", "Rua Origem", "1", "Bx", "01000000", "ANA SOUZA",
         "11122233344", "", "11987654321", "RUA DAS FLORES", "92", "JARDIM BELEM", "Suzano", "08613190", "SP", "BR", "CASA", "", "HLR"],
        ["2", "4002", "Rotalog", "Não Processado", "Entrega em Lote", "Orig", "Rua Origem", "1", "Bx", "01000000", "BETO LIMA",
         "55566677788", "", "11911112222", "RUA RUA 4", "S/N", "VILA NOVA", "SUZANO", "08615090", "SP", "BR", "", "", "NAKED"],
        ["3", "4003", "Rotalog", "Não Processado", "Entrega em Lote", "Orig", "Rua Origem", "1", "Bx", "01000000", "CAIO NUNES",
         "99988877766", "", "11922223333", "AV BRASIL", "10", "CENTRO", "MOGI DAS CRUZES", "08710000", "SP", "BR", "AP 3", "", "OUTRO"],
    ]
    return pd.DataFrame(linhas, columns=COLUNAS_PEDIDOS)


class TestToolbox(unittest.TestCase):
    def test_detecta_perfil_e_nao_confunde_com_css_ou_reintegra(self):
        self.assertEqual(pf.detectar_perfil(list(pedidos().columns), pf.PERFIS_PADRAO).nome, pf.TOOLBOX.nome)
        from tests.test_rotas import df_reintegra, df_tim
        self.assertEqual(pf.detectar_perfil(list(df_reintegra().columns), pf.PERFIS_PADRAO).nome, pf.REINTEGRA.nome)
        self.assertEqual(pf.detectar_perfil(list(df_tim().columns), pf.PERFIS_PADRAO).nome, pf.TIM_CSS.nome)

    def test_perfis_existentes_nao_mudaram(self):
        """Reintegra e CSS: mesmas colunas lidas e mesmo arquivo de saída de antes (regra do dono)."""
        self.assertEqual([c for c, _ in pf.REINTEGRA.saida],
                         ["BA", "Cliente", "Endereço completo", "Bairro", "Cep", "Cidade", "Telefone 1", "Complemento", "UF"])
        self.assertEqual([c for c, _ in pf.TIM_CSS.saida],
                         ["Número do Pedido", "Conta.2", "Nome", "Endereço completo", "Bairro", "CEP", "Cidade", "Telefone",
                          "Celular", "Informação adicional", "UF"])
        self.assertNotIn("cpf", pf.REINTEGRA.mapa)
        self.assertNotIn("itens", pf.TIM_CSS.mapa)

    def test_saida_igual_ao_modelo_rota_tim(self):
        can, faltando = pr.aplicar_perfil(pedidos(), pf.TOOLBOX)
        self.assertEqual(faltando, [])
        saida = pr.montar_saida(pr.ordenar_rota(can), pf.TOOLBOX, incluir_mapa=False)
        self.assertEqual(list(saida.columns), [
            "Pedido", "Destino - Nome", "Destino - CPF/CNPJ", "Destino - Celular", "Endereço Completo", "Destino - Bairro",
            "Destino - Cidade", "Destino - CEP", "Destino - UF", "Destino - País", "Destino - Informação adicional",
            "Descrição dos itens"])
        primeira = saida[saida["Pedido"] == "4001"].iloc[0]
        self.assertEqual(primeira["Destino - Celular"], "11987654321")       # só números, como no modelo
        self.assertEqual(primeira["Destino - CEP"], "08613190")              # sem hífen
        self.assertEqual(primeira["Destino - Cidade"], "SUZANO")             # maiúsculas
        self.assertEqual(primeira["Endereço Completo"], "RUA DAS FLORES N° 92")
        self.assertEqual(primeira["Descrição dos itens"], "HLR")

    def test_ordena_por_cep(self):
        can, _ = pr.aplicar_perfil(pedidos(), pf.TOOLBOX)
        ordem = pr.ordenar_rota(can)
        ceps = list(ordem.loc[ordem["cidade_up"] == "SUZANO", "cep_num"])
        self.assertEqual(ceps, sorted(ceps))

    def test_conferencia_avisa_chip_invalido_e_endereco_repetido(self):
        can, _ = pr.aplicar_perfil(pedidos(), pf.TOOLBOX)
        problemas = pr.checar_qualidade(can)
        textos = " | ".join(problemas["Problema"])
        self.assertIn("Tipo do chip não é HLR nem NAKED (OUTRO)", textos)
        self.assertIn("palavra repetida", textos)

    def test_empresas_sem_chip_nao_ganham_avisos_de_chip(self):
        from tests.test_rotas import df_reintegra
        can, _ = pr.aplicar_perfil(df_reintegra(), pf.REINTEGRA)
        self.assertFalse(pr.checar_qualidade(can)["Problema"].str.contains("chip").any())

    def test_mensagem_do_coletor_traz_total_hlr_naked(self):
        can, _ = pr.aplicar_perfil(pedidos(), pf.TOOLBOX)
        texto = mensagens.mensagem_rota("Toolbox", "GEOVAN", date(2026, 10, 27), can)
        self.assertIn("*HLR*: 1", texto)
        self.assertIn("*NAKED*: 1", texto)
        from tests.test_rotas import df_reintegra
        c2, _ = pr.aplicar_perfil(df_reintegra(), pf.REINTEGRA)
        self.assertNotIn("💳", mensagens.mensagem_rota("Reintegra", "X", date(2026, 10, 27), c2))


class TestSugestaoDeColunas(unittest.TestCase):
    def test_ignora_prefixo_destino_e_prefere_destino_a_origem(self):
        cols = list(pedidos().columns)
        self.assertEqual(pf.sugerir_coluna("nome", cols), "Destino - Nome")
        self.assertEqual(pf.sugerir_coluna("endereco", cols), "Destino - Logradouro")
        self.assertEqual(pf.sugerir_coluna("bairro", cols), "Destino - Bairro")
        self.assertEqual(pf.sugerir_coluna("cep", cols), "Destino - CEP")
        self.assertEqual(pf.sugerir_coluna("id", cols), "Pedido")
        self.assertEqual(pf.sugerir_coluna("telefone2", cols), "Destino - Celular")
        self.assertEqual(pf.sugerir_coluna("cpf", cols), "Destino - CPF/CNPJ")
        self.assertEqual(pf.sugerir_coluna("itens", cols), "Descrição dos itens")

    def test_sem_prefixo_e_sem_candidata(self):
        self.assertEqual(pf.sugerir_coluna("nome", ["BA", "Cliente", "Endereço"]), "Cliente")
        self.assertIsNone(pf.sugerir_coluna("cpf", ["BA", "Cliente"]))


class TestCadastrarNovaEmpresa(Base):
    """Regressão: a tela quebrava com StreamlitDuplicateElementKey ao anexar a planilha de exemplo."""

    def amostra(self):
        buf = io.BytesIO()
        pedidos().to_excel(buf, index=False)

        class Arq(io.BytesIO):
            name = "pedidos.xlsx"

            @property
            def size(self):
                return len(self.getvalue())
        return Arq(buf.getvalue())

    def test_anexar_planilha_nao_repete_chave_e_salva(self):
        from ui.adm import rotas
        usadas, repetidas = set(), []
        originais = {n: getattr(ST, n) for n in ("selectbox", "text_input", "text_area", "checkbox", "number_input")}

        def vigia(nome):
            def f(*a, key=None, **k):
                if key and key in usadas:
                    repetidas.append(key)
                if key:
                    usadas.add(key)
                return originais[nome](*a, key=key, **k)
            return f
        for n in originais:
            setattr(ST, n, vigia(n))
        try:
            sb = fakes.FakeSupabase()
            arq = self.amostra()
            ST.respostas.update({"rp_nome": "Empresa Nova", "rp_amostra": arq, "rp_salvar": True})
            with self.assertRaises(fakes.Reiniciar):  # salvar recarrega a tela
                rotas._nova_empresa(sb)
        finally:
            for n, f in originais.items():
                setattr(ST, n, f)
        self.assertEqual(repetidas, [])
        self.assertFalse([a for a in ST.avisos if a[0] == "error"], ST.avisos)
        salvo = sb.tabelas["rota_perfis"][-1]["definicao"]
        self.assertEqual(salvo["mapa"]["nome"], "Destino - Nome")
        self.assertEqual(salvo["mapa"]["cpf"], "Destino - CPF/CNPJ")


class TestMensagemWhats(unittest.TestCase):
    def test_novos_campos(self):
        extras = {"rua": "RUA A", "numero": "10", "bairro": "CENTRO", "cidade": "SUZANO", "protocolo": "4001"}
        texto = pr.preencher_mensagem("Oi {cliente}, sou {coletor}. {rua}, {numero} - {bairro}/{cidade} ({protocolo})",
                                      "MARIA DA SILVA", "GEOVAN", extras)
        self.assertEqual(texto, "Oi Maria, sou GEOVAN. RUA A, 10 - CENTRO/SUZANO (4001)")

    def test_campo_vazio_nao_deixa_buraco(self):
        self.assertEqual(pr.preencher_mensagem("Olá, {cliente}, tudo bem?", ""), "Olá, tudo bem?")

    def test_mensagem_antiga_continua_igual(self):
        antigo = pr.link_whatsapp("11987654321", "", "MARIA DA SILVA", "GEOVAN")
        self.assertIn("Ol%C3%A1%2C%20Maria%2C%20tudo%20bem%3F", antigo)

    def test_prontas_usam_apenas_campos_conhecidos(self):
        import re
        conhecidos = set(pr.CAMPOS_MENSAGEM)
        for nome, texto in pr.MODELOS_WHATS:
            self.assertFalse(set(re.findall(r"\{\w+\}", texto)) - conhecidos, nome)

    def test_planilha_traz_endereco_na_mensagem(self):
        can, _ = pr.aplicar_perfil(pedidos(), pf.TOOLBOX)
        saida = pr.montar_saida(can, pf.TOOLBOX, incluir_mapa=False, incluir_whats=True,
                                modelo_whats="{cliente}: {rua}, {numero} ({bairro})", coletor="X")
        self.assertIn("RUA%20DAS%20FLORES", saida["WhatsApp"].iloc[0])


class TestFechamentoWhatsApp(Base):
    def test_telefone_do_coletor(self):
        usuarios = [{"id": 2, "usuario": "ana", "nome_completo": "Ana Paula Souza", "cargo": "COLETOR"}]
        coletores = [{"id": 9, "nome_rota": "ANA", "telefone": "5511987654321", "usuario_id": 2},
                     {"id": 8, "nome_rota": "BETO", "telefone": "", "usuario_id": None}]
        self.assertEqual(vinculos.telefone_do_coletor(coletores, usuarios, "Ana Paula Souza"), "5511987654321")
        self.assertEqual(vinculos.telefone_do_coletor(coletores, usuarios, "Beto"), "")           # sem telefone
        self.assertEqual(vinculos.telefone_do_coletor(coletores, usuarios, "Desconhecido"), "")
        sem_login = [{"id": 1, "nome_rota": "CARLOS SOUZA", "telefone": "11911112222", "usuario_id": None}]
        self.assertEqual(vinculos.telefone_do_coletor(sem_login, [], "Carlos Souza"), "11911112222")

    def test_botao_aparece_e_o_texto_nao_traz_acrescentados(self):
        from ui.adm import fechamento
        from ui.adm.filtros import Filtro
        sb = banco()
        sb.tabelas["rota_coletores"] = [{"id": 1, "nome_rota": "ANA", "telefone": "5511987654321", "usuario_id": 2, "ativo": True}]
        links = []
        original = getattr(ST, "link_button", None)
        ST.link_button = lambda rotulo, url, **k: links.append((rotulo, url))
        try:
            fechamento.render(sb, Filtro(date(2026, 10, 1), date(2026, 10, 31), "Ana"))
        finally:
            if original is None:
                del ST.link_button
            else:
                ST.link_button = original
        self.assertFalse([a for a in ST.avisos if a[0] == "error"], ST.avisos)
        self.assertEqual(len(links), 1)
        rotulo, url = links[0]
        self.assertTrue(url.startswith("https://wa.me/5511987654321?text="))
        self.assertNotIn("crescent", url.lower())


if __name__ == "__main__":
    unittest.main()


class TestIAModeloDesligado(unittest.TestCase):
    def test_escolhe_flash_estavel_de_maior_versao(self):
        from disparador import ia
        nomes = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.5-flash", "gemini-3.5-flash-preview-x",
                 "gemini-2.5-pro", "gemini-3.5-flash-image"]
        self.assertEqual(ia.escolher_modelo_flash(nomes), "gemini-3.5-flash")
        self.assertIsNone(ia.escolher_modelo_flash(["gemini-2.5-pro"]))

    def test_modelo_antigo_404_tenta_o_flash_atual(self):
        from disparador import ia

        class R:
            def __init__(self, codigo, corpo=None):
                self.status_code, self._c = codigo, corpo

            def json(self):
                return self._c

        chamadas = []

        class Http:
            def post(self, url, **k):
                chamadas.append(url)
                if "gemini-2.0-flash" in url:
                    return R(404)
                return R(200, {"candidates": [{"content": {"parts": [{"text": '[{"assunto": "A", "texto": "Oi {nome} {protocolo}"}]'}]}}]})

            def get(self, url, **k):
                return R(200, {"models": [{"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
                                          {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]}]})
        itens = ia.gerar_modelos_ia("k", "gemini-2.0-flash", "x", "suave", 1, http=Http())
        self.assertEqual(itens[0]["assunto"], "A")
        self.assertTrue(chamadas[-1].endswith("gemini-3.5-flash:generateContent"))
        self.assertEqual(ia.MODELO_PADRAO, "gemini-flash-latest")


class TestTrabalhadoresSemStreamlit(unittest.TestCase):
    """O GitHub Actions não instala o Streamlit: os trabalhadores de e-mail e SMS não podem importá-lo (nem sem querer)."""

    def test_import_sem_streamlit(self):
        import subprocess
        import sys
        from pathlib import Path
        codigo = (
            "import sys, importlib, importlib.abc\n"
            "class B(importlib.abc.MetaPathFinder):\n"
            "    def find_spec(self, n, c=None, a=None):\n"
            "        if n.split('.')[0] in ('streamlit', 'streamlit_cookies_controller'):\n"
            "            raise ImportError('BLOQUEADO ' + n)\n"
            "sys.meta_path.insert(0, B())\n"
            "for m in ('disparador.worker', 'disparador.sms_worker', 'disparador.gatilho'):\n"
            "    importlib.import_module(m)\n"
            "print('ok')\n")
        raiz = Path(__file__).resolve().parent.parent
        r = subprocess.run([sys.executable, "-c", codigo], cwd=raiz, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertIn("ok", r.stdout)
