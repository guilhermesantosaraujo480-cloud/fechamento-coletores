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

## 🚚 Rotas → WhatsApp (nova aba)

1. Rode `migracao_v3.sql` no SQL Editor do Supabase (cria `rota_coletores`, `rota_grupos`, `rota_perfis`, `rota_envios`; já cadastra os 11 coletores dos scripts antigos).
2. Entre em **🚚 Rotas → 👷 Coletores** e vincule cada coletor ao login (há sugestão automática por nome) ou cadastre novos.
3. Em **🏢 Empresas e grupos**: cadastre os grupos de WhatsApp de cada empresa. Reintegra e TIM (CSS) já vêm prontas; outras empresas se cadastram mapeando as colunas de uma planilha de exemplo.
4. Em **🚚 Gerar e enviar**: suba a planilha → o sistema reconhece a empresa, confere problemas, divide por bairro, gera um .xlsx por coletor e envia ao grupo.
5. Envio automático exige um gateway não oficial (Evolution API ou Z-API) configurado em `WHATS_*` nos secrets. **Use um chip dedicado: há risco de bloqueio do número.** Sem gateway, o app roda em modo manual (baixar planilha + texto pronto para colar).
