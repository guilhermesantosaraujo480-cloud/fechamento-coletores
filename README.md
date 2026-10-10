# Sistema Vivo Coletas

Streamlit + Supabase. Coletas de aparelhos, vales, premiações, comprovantes de clientes e disparador de e-mails.

## Estrutura
```
app.py                 ponto de entrada (só monta a página e escolhe o módulo)
core/                  regras e acesso a dados (sem interface, testado)
  utils · config · consulta · financeiro · exportacao · armazenamento · auth · auditoria
  db · dados · sessao  (usam Streamlit: conexão, cache, sessão)
ui/                    telas
  login · conta · estilos · componentes
  adm/      visao_geral · coletas · fechamento · vales · premiacoes · usuarios · auditoria · emails · filtros
  coletor/  enviar · extrato · comprovantes
disparador/            e-mails (só ui.py usa Streamlit)
  utils · crypto · colunas · planilha · templates · envio_smtp · campanha · repositorio · metricas · ia · ui
tests/                 51 testes (unittest) com banco e Streamlit falsos
```

## Como publicar
1. Substitua os arquivos do projeto por esta pasta e **apague o `modulo_email.py` antigo**.
2. Supabase → SQL Editor: rode `migracao_v2.sql` (tabela `auditoria`, coluna `ativo`, índices).
3. Secrets: veja `secrets.exemplo.toml` (novo: `VALOR_POR_COLETA`).
4. `requirements.txt` mudou (`streamlit>=1.35`).
5. Todos precisarão entrar de novo uma vez.

## Testes
```
python -m unittest discover -s tests -t . -v
```
