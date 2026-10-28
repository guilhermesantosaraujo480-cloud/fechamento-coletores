"""core.compat: traduz use_container_width só quando a versão instalada não aceita mais."""
import types
import unittest

from core import compat


class TestCompat(unittest.TestCase):
    def test_versao_antiga_nao_mexe(self):
        chamadas = []
        st = types.SimpleNamespace(button=lambda rotulo, use_container_width=False, key=None: chamadas.append(use_container_width))
        original = st.button
        self.assertEqual(compat.instalar(st, delta_generator=types.SimpleNamespace()), [])
        self.assertIs(st.button, original)
        st.button("a", use_container_width=True)
        self.assertEqual(chamadas, [True])

    def test_versao_nova_traduz(self):
        recebido = {}

        def dataframe(dados, width="content", hide_index=None):
            recebido.update(width=width, dados=dados)

        st = types.SimpleNamespace(dataframe=dataframe)
        self.assertEqual(compat.instalar(st, delta_generator=types.SimpleNamespace()), ["dataframe"])
        st.dataframe([1], use_container_width=True, hide_index=True)
        self.assertEqual(recebido["width"], "stretch")
        st.dataframe([2], use_container_width=False)
        self.assertEqual(recebido["width"], "content")
        st.dataframe([3], width=300)
        self.assertEqual(recebido["width"], 300)

    def test_classe_delta_generator(self):
        class DG:
            def button(self, rotulo, width="content"):
                return width
        st = types.SimpleNamespace()
        compat.instalar(st, delta_generator=DG)
        self.assertEqual(DG().button("x", use_container_width=True), "stretch")
        compat.instalar(st, delta_generator=DG)  # segunda vez não embrulha de novo
        self.assertEqual(DG().button("x", use_container_width=True), "stretch")

    def test_sem_streamlit_instalado_nao_quebra(self):
        self.assertEqual(compat.instalar(types.SimpleNamespace(), delta_generator=None), [])


if __name__ == "__main__":
    unittest.main()
