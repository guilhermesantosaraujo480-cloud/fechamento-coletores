# Sistema de Coletas — Fechamento, Rotas, E-mails e Bipagem

Sistema interno (Streamlit + Supabase) para a operação de recolhimento de equipamentos (Vivo/TIM).
Uso do **administrador**; os coletores só enviam coletas/comprovantes e veem o próprio extrato.

## O que tem aqui

| Área | O que faz |
|---|---|
| 📊 Visão geral | Cards, ranking de coletores (com **Saldo anterior** e **A pagar**), aparelhos acrescentados |
| 📋 Coletas | Aprovar, recusar e **editar** (data, quantidade, acrescentados, valor); pago/não pago |
| 💵 Fechamento | Quinzena (1–15 / 16–fim), vales, premiações, saldo negativo levado para a quinzena seguinte, Excel |
| 📉 Vales / 🏅 Premiações | Lançamentos por coletor |
| 🚚 Rotas | Planilha da plataforma → uma planilha por coletor (com mapa, WhatsApp do cliente e avisos), envio no grupo, acompanhamento diário |
| 🔖 Bipagem | Lotes de OS + seriais extraídos de PDF; um **agente no seu computador** bipa na Reintegra |
| 📧 E-mails | Disparo em massa com contas rotativas, **variação de modelos**, fila em segundo plano, cliques, descadastros, IA para rascunhos |
| 👥 Usuários / 🛡️ Auditoria / ⚙️ Minha conta | Acesso, trilha de ações, troca de senha |

## Estrutura

```
app.py                 ponto de entrada (monta a página e escolhe o módulo)
core/                  regras: dinheiro (centavos), quinzenas, login, sessão, banco, Excel
ui/adm, ui/coletor     telas
disparador/            e-mails: modelos, variações, fila, trabalhador, SMTP, cliques, IA
rotas/                 leitura da planilha, perfis Reintegra/CSS, distribuição, WhatsApp
bipagem/               extração do PDF, regras dos seriais, fila e agente local (Selenium)
tests/                 testes automáticos (python -m unittest discover -s tests -t .)
migracao*.sql          criação das tabelas no Supabase (rodar em ordem)
.github/workflows/     disparador.yml (envio em segundo plano) e verificar.yml (confere arquivos)
verificar_projeto.py   confere se algum arquivo chegou vazio ou trocado
```

## Instalação (uma vez)

1. **Supabase → SQL Editor:** rode `migracao.sql`, `migracao_v2.sql`, `migracao_v3.sql`, `migracao_v4.sql` e `migracao_v5.sql`
   (pode rodar de novo sem problema; só cria o que falta). A variação de modelos **não precisa de SQL novo**.
2. **Streamlit Cloud → Settings → Secrets:** use o `secrets.exemplo.toml` como guia.
3. **GitHub → Settings → Secrets and variables → Actions:** crie `SUPABASE_URL`, `SUPABASE_KEY` (**service_role**) e
   `CHAVE_CRIPTO` (**igual** à do Streamlit).

## 📧 Variação de modelos (campanha com vários e-mails diferentes)

Em **📧 E-mails → 🚀 Disparos → Configuração**, escolha **🔀 Variar entre vários modelos**:

- Até **10 modelos** por campanha, escolhidos entre os 6 **[Pacote]** prontos, os padrões e os seus modelos salvos.
- Cada pessoa recebe **um** modelo; a distribuição é **embaralhada e proporcional ao peso** (peso 0 tira o modelo).
  Ex.: 2.000 e-mails × 6 modelos de peso 1 = 333/334 de cada.
- **Tom** do modelo: 🟢 suave, 🟡 neutro, 🔴 firme. O tom muda só a forma de pedir; **nenhum modelo do pacote inventa multa, prazo ou ameaça**.
- **Aparência**: cartão roxo ou e-mail simples. Assunto e texto também variam.
- Antes de enviar: escolha a variação na prévia e use **📨 Enviar teste das N variações** (chega um e-mail de cada).
- Funciona **agora, na tela** e **em segundo plano**; o modelo de cada pessoa fica gravado e não muda se a campanha for pausada/retomada.
- Resultado: na **⏱️ Fila**, "Ver andamento por modelo"; em **📈 Cliques → Desempenho por modelo** (enviados, erros,
  cliques de pessoas, taxa e descadastros de cada modelo).

## 📧 Disparo em segundo plano

Campanhas vão para a fila (tabelas `campanhas`/`campanha_destinos`) e um trabalhador no **GitHub Actions** envia, respeitando
intervalo e limite diário de cada conta. Pode fechar a página. Pausar, retomar, cancelar e reenviar erros na **⏱️ Fila**.
Para começar na hora, preencha `GITHUB_REPO`, `GITHUB_TOKEN_DISPARO`, `GITHUB_WORKFLOW = "disparador.yml"` e `GITHUB_BRANCH = "main"`.
Sem isso o trabalhador roda sozinho a cada 30 minutos.

## 🔖 Bipagem (agente local)

No seu computador: `pip install -r requirements-agente.txt`, copie `.env.exemplo` para `.env` (Supabase + login da Reintegra) e
execute `iniciar_agente.bat` (ou `python -m bipagem.agente`). Crie o lote no site (**🔖 Bipagem**) e o agente faz o resto.
O ponto (`.`) só é acrescentado ao serial quando a plataforma recusa por duplicidade.

## Se algo der errado ao subir os arquivos

Já aconteceu de arquivos chegarem **vazios** ou com o conteúdo de outro (site em branco, trabalhador falhando).
Por isso: **use "Add file → Upload files"** (não cole o texto), e rode `python verificar_projeto.py`.
O GitHub também roda essa conferência sozinho (Actions → *Verificar arquivos*): se ficar vermelha, ela diz qual arquivo está errado.
O arquivo `modulo_email.py` é a versão antiga e pode ser apagado.

## Testes

```
python -m unittest discover -s tests -t .
```
