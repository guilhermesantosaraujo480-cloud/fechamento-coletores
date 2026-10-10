"""Banco falso (Supabase) e Streamlit falso para testar sem instalar nada."""
import contextlib
import copy
import sys
import types


# ------------------------------------------------------------------- Supabase falso
class Resultado:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class Consulta:
    def __init__(self, db, nome):
        self.db, self.nome = db, nome
        self.op, self.payload, self.colunas, self.contar = "select", None, "*", False
        self.filtros, self._ordem, self._faixa, self._limite, self._conflito = [], None, None, None, None

    def select(self, colunas="*", count=None):
        self.op, self.colunas, self.contar = "select", colunas, count == "exact"
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def upsert(self, payload, on_conflict=None):
        self.op, self.payload, self._conflito = "upsert", payload, on_conflict
        return self

    def eq(self, col, val):
        self.filtros.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        self.filtros.append(lambda r: r.get(col) in list(vals))
        return self

    def gte(self, col, val):
        self.filtros.append(lambda r: r.get(col) is not None and str(r.get(col)) >= str(val))
        return self

    def lt(self, col, val):
        self.filtros.append(lambda r: r.get(col) is not None and str(r.get(col)) < str(val))
        return self

    def or_(self, expressao):
        """Só entende 'col.ilike.%x%,col2.ilike.%x%'."""
        partes = [p.split(".ilike.") for p in expressao.split(",")]
        self.filtros.append(lambda r: any(t.strip("%").lower() in str(r.get(c, "")).lower() for c, t in partes))
        return self

    def order(self, col, desc=False):
        self._ordem = (col, desc)
        return self

    def range(self, ini, fim):
        self._faixa = (ini, fim)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def _linhas(self):
        return [r for r in self.db.tabelas.setdefault(self.nome, []) if all(f(r) for f in self.filtros)]

    def execute(self):
        self.db.chamadas.append((self.nome, self.op))
        if self.nome in self.db.falhar_em:
            raise RuntimeError(f"falha simulada em {self.nome}")
        tabela = self.db.tabelas.setdefault(self.nome, [])
        if self.op == "insert":
            novas = self.payload if isinstance(self.payload, list) else [self.payload]
            saida = []
            for n in novas:
                linha = copy.deepcopy(n)
                if "id" not in linha and self.nome not in self.db.sem_id:
                    self.db.proximo_id += 1
                    linha["id"] = self.db.proximo_id
                tabela.append(linha)
                saida.append(copy.deepcopy(linha))
            return Resultado(saida)
        if self.op == "upsert":
            novas = self.payload if isinstance(self.payload, list) else [self.payload]
            for n in novas:
                existente = next((r for r in tabela if r.get(self._conflito) == n.get(self._conflito)), None)
                if existente:
                    existente.update(n)
                else:
                    tabela.append(copy.deepcopy(n))
            return Resultado(novas)
        alvo = self._linhas()
        if self.op == "update":
            for r in alvo:
                r.update(copy.deepcopy(self.payload))
            return Resultado(copy.deepcopy(alvo))
        if self.op == "delete":
            for r in alvo:
                tabela.remove(r)
            return Resultado(copy.deepcopy(alvo))
        total = len(alvo)
        if self._ordem:
            col, desc = self._ordem
            alvo = sorted(alvo, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        if self._faixa:
            alvo = alvo[self._faixa[0]: self._faixa[1] + 1]
        if self._limite is not None:
            alvo = alvo[: self._limite]
        alvo = copy.deepcopy(alvo)
        if self.colunas != "*":
            cols = [c.strip() for c in self.colunas.split(",")]
            alvo = [{c: r.get(c) for c in cols} for r in alvo]
        return Resultado(alvo, total if self.contar else None)


class Bucket:
    def __init__(self, db):
        self.db = db

    def upload(self, path, file, file_options=None):
        self.db.arquivos[path] = file

    def create_signed_url(self, caminho, segundos):
        return {"signedURL": f"https://exemplo.test/assinado/{caminho}?t=1"}


class Storage:
    def __init__(self, db):
        self.db = db

    def from_(self, bucket):
        return Bucket(self.db)


class FakeSupabase:
    def __init__(self, **tabelas):
        self.tabelas = {k: copy.deepcopy(v) for k, v in tabelas.items()}
        self.proximo_id = 1000
        self.arquivos, self.chamadas = {}, []
        self.falhar_em, self.sem_id = set(), {"descadastros"}
        self.storage = Storage(self)

    def table(self, nome):
        return Consulta(self, nome)


# --------------------------------------------------------------------- Streamlit falso
class Reiniciar(BaseException):  # como no Streamlit de verdade, não é capturado por `except Exception`
    pass


class Parar(BaseException):
    pass


class Estado(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class _Ctx:
    """Objeto que aceita qualquer chamada e funciona em `with`."""

    def __call__(self, *a, **k):
        return _Ctx()

    def __getattr__(self, nome):
        return _Ctx()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False


class Delegado(_Ctx):
    """Coluna/container/form: funciona em `with` e repassa os widgets para o Streamlit falso."""

    def __init__(self, st):
        self._st = st

    def __call__(self, *a, **k):
        return Delegado(self._st)

    def __getattr__(self, nome):
        return getattr(self._st, nome)


class FakeSt(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state, self.secrets, self.query_params = Estado(), {}, {}
        self.respostas = {}  # chave do widget -> valor a devolver (para simular cliques/entradas)
        self.sidebar = Delegado(self)
        self.column_config = _Ctx()
        self.avisos = []

    # decoradores de cache
    def _cache(self, *args, **kw):
        def aplicar(f):
            f.clear = lambda: None
            return f
        return aplicar(args[0]) if args and callable(args[0]) else aplicar

    cache_data = cache_resource = _cache

    # widgets de entrada
    def _resp(self, chave, padrao):
        return self.respostas.get(chave, padrao) if chave else padrao

    def button(self, rotulo, *a, key=None, **k):
        return bool(self._resp(key or rotulo, False))

    form_submit_button = button

    def text_input(self, rotulo, value="", *a, key=None, **k):
        return self._resp(key or rotulo, value)

    text_area = text_input

    def number_input(self, rotulo, *a, value=1, key=None, **k):
        return self._resp(key or rotulo, value)

    def checkbox(self, rotulo, value=False, *a, key=None, **k):
        return self._resp(key or rotulo, value)

    def date_input(self, rotulo, value=None, *a, key=None, **k):
        return self._resp(key or rotulo, value)

    def selectbox(self, rotulo, opcoes=(), index=0, *a, key=None, **k):
        opcoes = list(opcoes)
        padrao = opcoes[index] if opcoes and index is not None else None
        return self._resp(key or rotulo, padrao)

    def radio(self, rotulo, opcoes=(), *a, key=None, **k):
        opcoes = list(opcoes)
        return self._resp(key or rotulo, opcoes[0] if opcoes else None)

    def segmented_control(self, rotulo, opcoes=(), *a, default=None, key=None, **k):
        opcoes = list(opcoes)
        return self._resp(key or rotulo, default or (opcoes[0] if opcoes else None))

    def file_uploader(self, rotulo, *a, key=None, **k):
        return self._resp(key or rotulo, None)

    def data_editor(self, df, *a, key=None, **k):
        return self._resp(key, df)

    # layout
    def columns(self, spec, *a, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [Delegado(self) for _ in range(n)]

    def tabs(self, rotulos, *a, **k):
        return [Delegado(self) for _ in rotulos]

    def container(self, *a, **k):
        return Delegado(self)

    expander = form = spinner = popover = status = container

    def rerun(self):
        raise Reiniciar()

    def stop(self):
        raise Parar()

    def warning(self, texto="", *a, **k):
        self.avisos.append(("warning", str(texto)))

    def error(self, texto="", *a, **k):
        self.avisos.append(("error", str(texto)))

    def __getattr__(self, nome):  # markdown, caption, metric, dataframe, image, ... = não faz nada
        if nome.startswith("__"):
            raise AttributeError(nome)
        return _Ctx()


def instalar():
    """Coloca o Streamlit falso em sys.modules (só se o de verdade não estiver instalado)."""
    try:
        import streamlit  # noqa: F401
        if not isinstance(streamlit, FakeSt):
            return None
    except Exception:
        pass
    st = FakeSt()
    comp = types.ModuleType("streamlit.components")
    v1 = types.ModuleType("streamlit.components.v1")
    v1.html = lambda *a, **k: None
    comp.v1 = v1
    st.components = comp
    sys.modules.update({"streamlit": st, "streamlit.components": comp, "streamlit.components.v1": v1})
    cookies = types.ModuleType("streamlit_cookies_controller")

    class CookieController:
        def __init__(self):
            self.dados = {}

        def get(self, nome):
            return self.dados.get(nome)

        def set(self, nome, valor, **k):
            self.dados[nome] = valor

        def remove(self, nome):
            self.dados.pop(nome, None)

    cookies.CookieController = CookieController
    sys.modules["streamlit_cookies_controller"] = cookies
    return st


@contextlib.contextmanager
def silencio():
    yield
