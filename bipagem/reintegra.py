"""Navegador (Selenium) da plataforma da Reintegra. Os passos, seletores e pausas são os do seu script
BEEBAR_APARELHO_FINAL.py; o que mudou é só o entorno: recuperação de erro, foto da tela quando falha,
detecção do alerta sem esperar à toa e sessão que reabre sozinha se cair.

`pausa` multiplica TODAS as esperas fixas (1.0 = igual ao script antigo). Depois que estiver tudo estável,
experimente 0.6 (variável de ambiente BIPAGEM_PAUSA) para ir mais rápido."""
import os
import time

try:
    from selenium import webdriver
    from selenium.common.exceptions import NoAlertPresentException, TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
except ImportError:  # o site (Streamlit) importa este arquivo sem precisar do Selenium
    webdriver = None

URL = "https://reintegra.codebox.com.br/os_lista"


class ErroPlataforma(Exception):
    pass


class PlataformaReintegra:
    def __init__(self, usuario, senha, pausa=1.0, headless=False, pasta_logs="bipagem_logs"):
        if webdriver is None:
            raise RuntimeError("Selenium não instalado. Rode: pip install -r requirements-agente.txt")
        self.usuario, self.senha, self.pausa = usuario, senha, float(pausa)
        self.pasta_logs = pasta_logs
        self.ultimo_alerta = ""
        opcoes = webdriver.ChromeOptions()
        opcoes.add_argument("--start-maximized")
        if headless:
            opcoes.add_argument("--headless=new")
            opcoes.add_argument("--window-size=1920,1080")
        self.driver = webdriver.Chrome(options=opcoes)
        self.wait = WebDriverWait(self.driver, 15)

    # ------------------------------------------------------------------ utilidades
    def _p(self, segundos):
        time.sleep(segundos * self.pausa)

    def _clicavel(self, por, seletor):
        return self.wait.until(EC.element_to_be_clickable((por, seletor)))

    def _js_click(self, elemento):
        self.driver.execute_script("arguments[0].click();", elemento)

    def _alerta(self, espera):
        """Texto do alerta (já aceito) ou None se não apareceu em `espera` segundos."""
        try:
            WebDriverWait(self.driver, max(espera, 0.5)).until(EC.alert_is_present())
            alerta = self.driver.switch_to.alert
            texto = alerta.text
            alerta.accept()
            return texto
        except (TimeoutException, NoAlertPresentException):
            return None

    # ----------------------------------------------------------------------- sessão
    def entrar(self):
        d = self.driver
        d.get(URL)
        self._p(2)
        campo = self._clicavel(By.ID, "username")
        campo.clear()
        campo.send_keys(self.usuario)
        self._p(2)
        campo = self._clicavel(By.ID, "password")
        campo.clear()
        campo.send_keys(self.senha)
        self._p(2)
        self._clicavel(By.XPATH, "//button[@type='submit']").click()
        self._p(3)

    def abrir_lista(self):
        """Menu Ordens de Serviço -> status 'Coletado App' -> Localizar."""
        self._clicavel(By.XPATH, "//a[contains(text(), 'Ordens de Serviço')]").click()
        self._p(3)
        Select(self._clicavel(By.ID, "ftrCodigoStatus")).select_by_visible_text("Coletado App")
        self._p(2)
        self._p(2)
        botao = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button.btn-filtrar")))
        self._js_click(botao)
        self._p(4)

    def garantir_sessao(self):
        """Se a plataforma derrubou a sessão (volta o formulário de login), entra de novo."""
        if self.driver.find_elements(By.ID, "username"):
            self.entrar()
            self.abrir_lista()

    def recuperar(self):
        """Depois de uma falha: fecha alerta, volta para a lista e refaz o filtro."""
        self._alerta(0.5)
        self.driver.get(URL)
        self._p(2)
        if self.driver.find_elements(By.ID, "username"):
            self.entrar()
        self.abrir_lista()

    def fechar(self):
        try:
            self.driver.quit()
        except Exception:  # noqa: BLE001
            pass

    # -------------------------------------------------------------------------- lista
    def _links(self):
        return self.driver.find_elements(By.XPATH, "//a[@class='ajax-modal' and @data-url='os_cadastro']")

    def listar_os(self):
        textos = []
        for el in self._links():
            try:
                t = el.text.strip()
            except Exception:  # noqa: BLE001 — elemento trocado no meio da leitura
                continue
            if t:
                textos.append(t)
        return textos

    def abrir_os(self, numero):
        for el in self._links():
            try:
                if el.text.strip() == numero:
                    self._js_click(el)
                    self._p(3)
                    return
            except Exception:  # noqa: BLE001
                continue
        raise ErroPlataforma(f"OS {numero} não está mais na lista")

    # ------------------------------------------------------------------------ uma OS
    def iniciar_retirada(self):
        self._clicavel(By.ID, "btnEncerrarOS").click()
        self._p(3)
        sim = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.retirarEquipamento")))
        self._js_click(sim)
        self._p(3)

    def selecionar_equipamento(self, codigo):
        self._clicavel(By.XPATH, "//button[@data-id='CodigoEquipamentoOS']").click()
        self._p(2)
        self.driver.switch_to.active_element.send_keys(codigo)
        self._p(2)
        self.driver.switch_to.active_element.send_keys(Keys.ENTER)
        self._p(3)

    def tentar_serial(self, serial, forte=False):
        """Digita o serial e clica em Adicionar. Devolve 'ok' ou 'duplicado' (a plataforma abriu um alerta)."""
        campo = self._clicavel(By.ID, "EquipamentosSerieOS")
        if forte:  # depois de um alerta o campo precisa ser limpo "à mão" (igual ao script antigo)
            campo.click()
            self._p(1)
            campo.send_keys(Keys.CONTROL, "a")
            campo.send_keys(Keys.BACKSPACE)
            self._p(1)
        else:
            campo.clear()
        campo.send_keys(serial)
        self._p(2)
        self._clicavel(By.CSS_SELECTOR, "a.adicionarEquipamento").click()
        texto = self._alerta(2 * self.pausa)  # sai assim que o alerta aparece; sem alerta espera os mesmos 2 s de antes
        if texto is None:
            return "ok"
        self.ultimo_alerta = texto
        self._p(3)
        return "duplicado"

    def salvar_perifericos(self):
        botao = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "a.addPerifericos")))
        self._js_click(botao)
        self._p(3)

    def finalizar(self, data):
        campo = self._clicavel(By.ID, "DataColeta")
        self.driver.execute_script("arguments[0].value = arguments[1];", campo, data)
        self._p(2)
        self._clicavel(By.ID, "encerrarOS").click()
        self._alerta(15)  # confirmação do navegador; se não aparecer, segue (como antes)

    def aguardar_retorno_lista(self):
        self._p(5)

    # ---------------------------------------------------------------------- diagnóstico
    def registrar_falha(self, numero, mensagem):
        """Guarda uma foto da tela do momento do erro em bipagem_logs/ (ajuda a descobrir o que mudou na plataforma)."""
        try:
            os.makedirs(self.pasta_logs, exist_ok=True)
            nome = f"erro_{time.strftime('%Y%m%d_%H%M%S')}_{str(numero)[:30]}.png".replace("/", "-")
            self.driver.save_screenshot(os.path.join(self.pasta_logs, nome))
        except Exception:  # noqa: BLE001
            pass
