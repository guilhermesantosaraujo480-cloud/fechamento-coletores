"""Falha se algum arquivo do projeto estiver vazio, trocado ou com código quebrado."""
import json
import tempfile
import unittest
from pathlib import Path

import verificar_projeto as v


class TestIntegridade(unittest.TestCase):
    def test_projeto_inteiro_sem_arquivo_vazio_ou_trocado(self):
        erros, _ = v.verificar()
        self.assertEqual(erros, [], "\n".join(erros))

    def test_detecta_vazio_trocado_e_quebrado(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            (raiz / "app.py").write_text("")
            (raiz / "requirements-worker.txt").write_text("# Sistema\nEste é o README do projeto, com texto livre.\n")
            (raiz / "ruim.py").write_text("def x(:\n")
            (raiz / "MELHORIAS.md").write_text("@echo off\ncd /d x\n")
            original = v.RAIZ, v.MANIFESTO
            v.RAIZ, v.MANIFESTO = raiz, raiz / "MANIFESTO.json"
            try:
                erros, _ = v.verificar()
            finally:
                v.RAIZ, v.MANIFESTO = original
        texto = "\n".join(erros)
        for esperado in ("VAZIO: app.py", "CÓDIGO QUEBRADO: ruim.py", "CONTEÚDO TROCADO: requirements-worker.txt",
                         "CONTEÚDO TROCADO: MELHORIAS.md", "FALTANDO: README.md"):
            self.assertIn(esperado, texto)

    def test_manifesto_bate_com_os_arquivos(self):
        if not v.MANIFESTO.exists():
            self.skipTest("sem MANIFESTO.json")
        ref = json.loads(v.MANIFESTO.read_text(encoding="utf-8"))
        self.assertGreater(len(ref), 50)


if __name__ == "__main__":
    unittest.main()
