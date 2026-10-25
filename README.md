# Sistema de Coletas — Fechamento, Rotas, E-mails e Bipagem

Sistema interno (Streamlit + Supabase) da operação de recolhimento de equipamentos (Vivo/TIM), com as empresas
parceiras **Reintegra** e **CSS**. O **administrador** usa tudo; os **coletores** só enviam coletas, consultam o
próprio extrato e buscam comprovantes de clientes.

> **Para quem for alterar este projeto (inclusive o Claude):** leia primeiro as seções
> **"Regras que não podem quebrar"** e **"Histórico de mudanças"**. O dono do projeto pediu, em todas as rodadas:
> *"o que já funciona, não mexer"*. Mudanças novas devem ser **aditivas** e vir com testes.

Índice: 1 Visão geral · 2 Mapa dos arquivos · 3 Telas · 4 Regras que não podem quebrar · 5 Banco de dados ·
6 Configuração · 7 E-mails · 8 Rotas · 9 Bipagem · 10 Desempenho e custo · 11 Segurança · 12 Como atualizar ·
13 Testes · 14 Problemas conhecidos · 15 Histórico de mudanças · 16 Pendências

---

## 1. Visão geral

| Peça | Onde roda | Para quê |
|---|---|---|
| App web (Streamlit Cloud) | nuvem | todas as telas (admin e coletor) |
| Banco + fotos (Supabase) | nuvem | dados, fila de e-mails, fotos privadas dos comprovantes |
| Trabalhador de e-mails (GitHub Actions) | nuvem | envia a fila em segundo plano (`.github/workflows/disparador.yml`) |
| Verificação de arquivos (GitHub Actions) | nuvem | acusa arquivo vazio/trocado a cada envio (`verificar.yml`) |
| Agente da bipagem (Selenium) | **computador do administrador** | bipa seriais na Reintegra (`python -m bipagem.agente`) |

Fluxo geral: coletor envia foto + quantidade → administrador aprova/edita → o **Fechamento** soma por quinzena,
desconta vales, soma premiações e leva saldo negativo para a quinzena seguinte.

---

## 2. Mapa dos arquivos

```
app.py                      Entrada. Monta a página, faz login e carrega SÓ a tela aberta (importação sob demanda).
                            PAGINAS_ADM / PAGINAS_COLETOR = menu -> módulo. ?debug=1 mostra cada etapa e a versão do Streamlit.
verificar_projeto.py        Confere arquivos vazios/trocados/quebrados. MANIFESTO.json = lista de referência (tamanho + hash).
requirements.txt            App web.   requirements-worker.txt = trabalhador de e-mails.   requirements-agente.txt = bipagem.
secrets.exemplo.toml        Modelo dos secrets do Streamlit.   .env.exemplo = modelo do .env do agente da bipagem.
iniciar_agente.bat          Liga o agente da bipagem no Windows.
migracao*.sql               Criação/ajuste das tabelas (rodar em ordem; podem rodar de novo).

core/                       Regras de negócio e infraestrutura (sem telas)
  utils.py                  Datas, dinheiro (brl), quinzenas (limites_quinzena, PERIODOS), em_lotes, escapar
  config.py                 cfg(): lê st.secrets sem quebrar;  valor_por_coleta()
  db.py                     Conexão única com o Supabase (cache_resource)
  consulta.py               buscar_todos (pagina de 1000 em 1000), contar, filtros no servidor
  financeiro.py             Fechamento em CENTAVOS, quinzenas, saldo anterior, acréscimos, resumo por coletor
  dados.py                  Carregadores com cache curto (30 s; saldos 5 min). TODA gravação chama dados.invalidar()
  armazenamento.py          Fotos: valida, abre com pouca memória, compacta (1280 px), gera miniatura (320 px), links assinados
  auth.py / sessao.py       Login (bcrypt), limite de tentativas, token de sessão (só o hash no banco) + cookie
  exportacao.py             Excel (neutraliza fórmulas, links Mapa/WhatsApp)
  auditoria.py              Trilha de quem fez o quê

ui/                         Telas
  login.py, conta.py, estilos.py (CSS, inclui ajustes de celular), componentes.py (cartao, metricas, mostrar_foto...)
  adm/                      visao_geral, coletas, fechamento, vales, premiacoes, usuarios, auditoria, emails, rotas, bipagem, filtros
  coletor/                  enviar (foto+quantidade), extrato, comprovantes, camera.py + camera_leve/index.html (câmera leve opcional)

disparador/                 E-mails (só ui.py usa Streamlit)
  colunas.py, planilha.py   Reconhece colunas da planilha; triagem (inválido, duplicado, descadastrado, já enviado)
  templates.py              Modelos padrão 1/2, modelos salvos, layouts cartão/simples, HTML + texto puro
  variacoes.py              Mistura de até 10 modelos por campanha (tom suave/neutro/firme), pacote de 6 modelos prontos
  campanha.py               Loop de disparo (testável, sem Streamlit)
  envio_smtp.py, crypto.py  SMTP Gmail com rodízio de contas; senhas de app criptografadas (Fernet)
  fila.py, worker.py        Fila no banco + trabalhador (GitHub Actions); gatilho.py acorda o trabalhador na hora
  repositorio.py            Acesso ao banco do disparador (ja_enviados aceita só os protocolos da campanha)
  metricas.py               Cliques: pessoa x robô; desempenho por modelo
  ia.py                     Gemini grátis: só RASCUNHOS (humano aprova)

rotas/                      Planilha da operadora -> rota por coletor -> WhatsApp (perfis, nomes, avisos, distribuição, acompanhamento)
bipagem/                    PDF -> (OS, serial); regras do ponto; fila de lotes; motor; navegador Selenium; agente local
tests/                      Testes automáticos (fakes de Streamlit e Supabase em tests/fakes.py)
.github/workflows/          disparador.yml (envio), verificar.yml (arquivos), manter_ativo.yml (ping opcional)
```

---

## 3. Telas

### Administrador (menu lateral)
| Tela | O que faz | Tabelas |
|---|---|---|
| 📊 Visão geral | Cards, ranking de coletores com **Saldo anterior** e **A pagar**, tabela de **acrescentados** (só aqui e em Coletas) | coletas, vales_coleta, premiacoes |
| 📋 Coletas | Pendentes (miniatura da foto, aprovar/recusar/**editar**), lançamentos do período (status/pago), "aprovar todas", "marcar pagas" | coletas |
| 💵 Fechamento | Por quinzena; vales; premiações; saldo negativo levado adiante; Excel | coletas, vales_coleta, premiacoes |
| 📉 Vales / 🏅 Premiações | Lançar, ver comprovante (miniatura), excluir | vales_coleta, premiacoes |
| 🚚 Rotas | Gerar e enviar, Acompanhamento, Coletores, Empresas e grupos, Histórico | rota_* |
| 🔖 Bipagem | Novo lote (PDF/lista de seriais) e acompanhamento dos lotes | bipagem_* |
| 📧 E-mails | 🚀 Disparos · ⏱️ Fila · ✉️ Modelos · 🔑 Contas · 🚫 Descadastros · 📜 Histórico · 📈 Cliques | campanhas, envios_email... |
| 👥 Usuários · 🛡️ Auditoria · ⚙️ Minha conta | Acesso, trilha de ações, troca de senha | usuarios, auditoria |

### Coletor
📲 Enviar coleta (quantidade + foto) · 📊 Meu extrato (com saldo anterior) · 🔍 Comprovantes (busca por OS/nome) · ⚙️ Minha conta.

---

## 4. Regras que não podem quebrar

1. **Dinheiro em centavos inteiros** (`core/financeiro.py`). Nunca somar `float` direto.
2. **Quinzenas:** 1–15 e 16–fim do mês. Fechamentos são por quinzena.
3. **Saldo anterior:** se o líquido de uma quinzena é negativo (vales > produção), a dívida passa para a seguinte e é abatida
   sozinha (até 12 quinzenas para trás). A Visão geral usa **A pagar** (não o líquido) no ranking.
4. **Aparelhos acrescentados:** `quantidade` e `valor_total` guardam o **total pago**; `qtd_acrescimo` é só controle do
   administrador. Aparece **apenas** na Visão geral e em Coletas. **Nunca** no Fechamento, no extrato do coletor nem no Excel.
5. **Toda gravação chama `dados.invalidar()`** (senão as telas mostram dado velho por até 30 s).
6. **Não reenviar e-mail:** a triagem pula quem já está em `envios_email` (status enviado), descadastrados, inválidos e
   duplicados. `ja_enviados` filtrado por protocolo é equivalente ao completo; com protocolo vazio/estranho lê tudo.
7. **A IA só gera rascunho** de modelo. Nenhum modelo inventa multa, prazo ou ameaça; `VALOR_MULTA` só entra se configurado.
8. **Um trabalhador por vez** na fila (reserva `lease_ate` + `concurrency` no workflow). Envio interrompido volta para a fila.
9. **Bipagem:** o ponto `.` só é acrescentado ao serial quando a plataforma recusa por duplicidade (até 6 pontos); só avança o
   serial quando a plataforma aceita; depois de gravar dados parciais a OS vira "verificar" (nunca repete sozinha).
10. **Fotos nunca públicas:** guardar só o **caminho**; mostrar por link assinado temporário. Fotos novas têm nome `*_m.jpg`
    (com miniatura `*_t.jpg`); fotos antigas continuam funcionando sem miniatura.
11. **Segredos nunca no GitHub** (`.gitignore` bloqueia `secrets.toml` e `.env`).
12. **Arquivos nunca vazios:** `python verificar_projeto.py` e o GitHub conferem. Use "Upload files", não copie e cole.
13. **Mudança nova = aditiva + teste.** Telas que já funcionam não são reescritas sem pedido.

---

## 5. Banco de dados (Supabase)

Rode em ordem no **SQL Editor** (todos podem ser repetidos sem problema; foram testados num Postgres 16):

| Arquivo | O que cria |
|---|---|
| `migracao.sql` | envios_email, descadastros, modelos_email (+ passos opcionais de segurança/RLS) |
| `migracao_v2.sql` | auditoria, `usuarios.ativo`, índices |
| `migracao_v3.sql` | rota_coletores, rota_grupos, rota_perfis, rota_envios |
| `migracao_v4.sql` | campanhas, campanha_destinos (fila), `rota_coletores.tipo`, rota_apelidos, rota_snapshots |
| `migracao_v5.sql` | `coletas.qtd_acrescimo`, bipagem_lotes, bipagem_itens, bipagem_agente |
| `migracao_v6.sql` | **índices de desempenho** + função opcional `limpar_historico_antigo()` |

Tabelas que já existiam antes das migrações (criadas na primeira versão): `usuarios`, `coletas`, `vales_coleta`,
`premiacoes`, `comprovantes_clientes`, `logs_comprovantes`, `contas_email`, `cliques_email` (preenchida pela Edge Function).

**Variação de modelos não precisa de SQL:** a escolha do modelo de cada pessoa fica em `campanha_destinos.dados._variante`
e o nome do modelo vai em `envios_email.modelo`.

**Limpeza (opcional, manual):** `select limpar_historico_antigo();` apaga só dados técnicos antigos (destinos de campanhas
concluídas, itens de bipagem de lotes terminados, fotografias de rota, auditoria e buscas > 1 ano). **Nunca** apaga coletas,
vales, premiações, usuários, `envios_email` (evita reenvio) nem descadastros.

---

## 6. Configuração

**Streamlit Cloud → Settings → Secrets** (modelo completo em `secrets.exemplo.toml`):
`SUPABASE_URL`, `SUPABASE_KEY` (service_role), `EMPRESA_NOME`, `EMPRESA_IDENTIFICACAO`, `WHATSAPP_NUMERO`, `CHAVE_CRIPTO`,
`URL_FUNCAO_CLIQUE`, `VALOR_MULTA`, `VALOR_POR_COLETA` (padrão 10), `GEMINI_API_KEY`, `GEMINI_MODEL`,
`GITHUB_REPO`, `GITHUB_TOKEN_DISPARO`, `GITHUB_WORKFLOW="disparador.yml"`, `GITHUB_BRANCH="main"`,
`WHATS_PROVEDOR`, `WHATS_API_URL`, `WHATS_API_KEY`, `WHATS_INSTANCIA`, `WHATS_CLIENT_TOKEN`, **`FOTO_LEVE`** (câmera leve; ver seção 10).

**GitHub → Settings → Secrets and variables → Actions:**
- *Secrets:* `SUPABASE_URL`, `SUPABASE_KEY` (**service_role**), `CHAVE_CRIPTO` (**igual** à do Streamlit).
- *Variables (opcional):* `APP_URL` (endereço do app) para o `manter_ativo.yml`.

**Agente da bipagem (seu computador):** `pip install -r requirements-agente.txt`; copie `.env.exemplo` para `.env`
(`SUPABASE_URL`, `SUPABASE_KEY`, `USUARIO`, `SENHA`); execute `iniciar_agente.bat`.

> Atenção: o navegador traduz páginas do GitHub. Nomes como `disparador.yml` e `main` devem ser digitados **sem tradução**.

---

## 7. E-mails

**Fluxo:** planilha → colunas reconhecidas → triagem → prévia/teste → enviar **agora** ou **em segundo plano** (fila).
Contas Gmail com senha de app (criptografada), limite diário por conta, rodízio, intervalo aleatório entre envios,
HTML + texto puro, `List-Unsubscribe`, botão de WhatsApp com contagem de cliques (pessoa x robô).

**Variação de modelos (2.000 e-mails × 6 modelos):** em *Disparos → Configuração* escolha "🔀 Variar entre vários modelos".
Até 10 modelos (6 prontos `[Pacote]`, os padrões e os salvos), com **peso**; cada pessoa recebe um só, embaralhado e
proporcional. Tom 🟢 suave / 🟡 neutro / 🔴 firme (só muda a forma de pedir) e aparência cartão/simples. Há prévia por variação e
**"Enviar teste das N variações"**. Resultado: *Fila → Ver andamento por modelo* e *Cliques → Desempenho por modelo*.

**Segundo plano:** `campanhas` + `campanha_destinos`; o trabalhador roda a cada 30 min e na hora quando o app o aciona.
Pausar, retomar, cancelar, reenviar erros. Se o limite diário acabar, continua no dia seguinte.

**Plano futuro:** domínio `@rllogisticareversa.com.br` (3 a 5 caixas, subdomínio de campanha, SPF/DKIM/DMARC, aquecimento),
exigindo adaptar o SMTP (hoje Gmail) para qualquer provedor.

---

## 8. Rotas

Planilha da operadora → **perfil** da empresa (Reintegra: BA/Cliente/Coletor; CSS: Número do Pedido/Transportador) →
nomes ligados aos coletores (e **apelidos**) → rota por coletor em Excel (com **Mapa**, **WhatsApp do cliente** e **Avisos**)
→ envio no grupo (Evolution/Z-API, risco de banimento: chip dedicado) ou manual por link.
Tipos de coletor: normal, **retentativa**, **depósito**. Sugestão para OS sem dono: "mudou-se" → depósito; "já foi à rua" →
retentativa; senão território/CEP/cidade/carga. **Acompanhamento:** fotografia diária (`rota_snapshots`) para ver quem avançou.
Avisos por OS (prioridade, agenda, área de risco, reaberta, ausente, dias na fila) **só informam**; nada é excluído.

---

## 9. Bipagem

Site: cria o **lote** (OS + seriais do PDF, 1 ou 2 aparelhos por OS, tipos 002 HGU / 001 IPTV / 008 WIFI-6 / 23 ADSL).
Agente local: abre o Chrome, entra na Reintegra com **seu** login e bipa. Pode parar/retomar pelo site.
Com poucos seriais para muitas OS, a lista **recomeça com `.`, depois `..`** (até 6). Teste real ainda pendente: use
primeiro um lote de **1 ordem**.

---

## 10. Desempenho e custo (o que foi feito e por quê)

| Medida | Efeito |
|---|---|
| **Importação sob demanda** (`app.py`) | O coletor não carrega Rotas/E-mails/Bipagem: menos memória e abertura mais rápida |
| **Foto aberta com pouca memória** (`Image.draft`) | Foto de 12 MP deixa de ocupar ~50 MB de RAM no servidor |
| **Miniatura de 320 px (~20 KB)** | Listas de aprovação/extrato gastam ~10× menos internet; "🔍 Ver foto inteira" abre sob demanda |
| **Foto principal 1280 px, JPEG 78** | ~150–250 KB (antes: 3–6 MB do celular) |
| **Prévia pela foto compacta + cálculo único** | Mexer na quantidade não reprocessa a foto nem reenvia imagem grande |
| **Câmera leve (opcional, `FOTO_LEVE="sim"`)** | O próprio celular reduz a foto **antes** de enviar (upload de ~200 KB em vez de MBs) |
| **Colunas enxutas** nas consultas financeiras | Sem `foto_url`/descrições nos saldos; sem lista de pendentes duplicada |
| **Cache:** saldos 5 min, demais 30 s, últimos envios do coletor 30 s | Menos idas ao banco por clique |
| **`ja_enviados` por protocolo da campanha** | Triagem não cresce com o histórico inteiro de e-mails |
| **Cliques/Histórico com período** (padrão 90 dias / 500 linhas) | Telas continuam rápidas com o histórico crescendo |
| **Índices (`migracao_v6.sql`)** | Filtros por data/coletor/status e buscas de e-mail ficam rápidos com muitas linhas |
| **Limpeza opcional** (`limpar_historico_antigo`) | Mantém o banco pequeno sem perder financeiro nem proteção contra reenvio |
| **`manter_ativo.yml`** (opcional) | Evita o app "dormir" (melhor esforço; não é garantia) |

**Câmera leve:** vem **desligada**. Para testar: coloque `FOTO_LEVE = "sim"` nos secrets, abra o app no **seu celular**, envie uma
coleta de teste e confira que a foto chegou legível na aprovação. Se algo falhar, o envio "do jeito normal" fica logo abaixo e
basta apagar a linha dos secrets para voltar.

**Estimativa de espaço (plano gratuito do Supabase — confira os limites atuais no painel):** ~200 KB por foto ⇒ 20 envios/dia
≈ 120 MB/mês de fotos. Acompanhe *Storage* no painel; fotos muito antigas de coletas já pagas podem ser arquivadas à parte.

---

## 11. Segurança

Senhas com bcrypt · sessão por token (banco guarda só o hash) · limite de tentativas de login · senhas de e-mail com Fernet
(`CHAVE_CRIPTO`) · fotos em bucket privado com link temporário · Excel com fórmulas neutralizadas · HTML de e-mail com dados
do cliente escapados · trilha de auditoria · `service_role` só em servidores/computador do administrador (nunca no navegador).

---

## 12. Como atualizar o sistema

1. Receba o pacote (`so_o_que_mudou.zip`), extraia e copie para a pasta do projeto **mantendo as pastas**.
2. **GitHub Desktop:** *Repository → Show in Explorer* → colar/substituir → conferir em *Changes* → *Commit to main* → *Push origin*.
   **Navegador:** *Add file → Upload files* (entrando em cada pasta antes de subir).
3. Rode `python verificar_projeto.py` (ou veja a aba **Actions → Verificar arquivos** ficar verde).
4. Se o pacote traz SQL novo (`migracao_vN.sql`), rode no Supabase **antes** de usar a novidade.
5. O Streamlit Cloud atualiza sozinho em ~1 minuto. Se ficar em branco, abra `?debug=1` no fim do endereço.
6. Depois de mudar algo de propósito, gere o novo `MANIFESTO.json` com `python verificar_projeto.py --gerar`.

---

## 13. Testes

```
python -m unittest discover -s tests -t .
```
Cobrem finanças, auth, fotos/miniaturas, e-mails (triagem, variações, fila, trabalhador, recuperação de queda), rotas,
bipagem, telas (com Streamlit e Supabase simulados) e integridade dos arquivos. **Limite:** o Streamlit simulado não
enxerga problemas de aparência; teste visualmente no navegador e no celular após cada mudança de tela.

---

## 14. Problemas conhecidos e como resolver

| Sintoma | Causa provável | Solução |
|---|---|---|
| Site em branco | `app.py` (ou outro arquivo) chegou vazio | `python verificar_projeto.py`; subir de novo por "Upload files"; abrir `?debug=1` |
| Actions falha ao instalar ("exit code 1") | `requirements-worker.txt` com texto errado | Verificação de arquivos acusa; subir o arquivo correto |
| Erro 422 ao acionar o trabalhador | Nome do workflow/branch traduzido pelo navegador | `GITHUB_WORKFLOW="disparador.yml"`, `GITHUB_BRANCH="main"` |
| "Nenhuma conta de e-mail ativa/legível" | `CHAVE_CRIPTO` diferente entre Streamlit e GitHub, ou `SUPABASE_KEY` não é service_role | Igualar a chave; usar service_role no GitHub |
| Visão geral com A pagar errado | Saldo anterior não considerado | Já corrigido (ranking usa **A pagar**) |
| Erro citando `qtd_acrescimo` | `migracao_v5.sql` não rodou | Rodar no Supabase |
| App lento/antigo após muito uso | Cache ou banco sem índices | Rodar `migracao_v6.sql`; ver seção 10 |
| Atualização futura quebra telas | Streamlit novo mudou algo (ex.: `use_container_width` está sendo substituído por `width`) | Abrir `?debug=1`, ver a versão e fixar `streamlit==VERSÃO` no `requirements.txt` |

---

## 15. Histórico de mudanças

1. **E-mails, primeira rodada:** correção de segurança (hash de senha, token), histórico, descadastro, IA gratuita (rascunhos).
2. **Refatoração em módulos** (`core`, `ui`, `disparador`), layout novo, painel do coletor, testes automáticos.
3. **Quinzenas e saldo anterior**; ranking com *A pagar*; correção do saldo negativo da quinzena passada.
4. **Aba Rotas:** perfis Reintegra/CSS, apelidos, tipos de coletor, avisos, sugestão, acompanhamento, coluna WhatsApp, envio.
5. **Disparo em segundo plano** (fila + GitHub Actions), pausar/retomar/cancelar, gatilho imediato.
6. **Bipagem** (site + agente local), edição de coletas na aprovação e **aparelhos acrescentados**.
7. **Diagnóstico de arquivos vazios/trocados** no GitHub (`app.py`, `requirements-worker.txt`, `.gitignore`, README).
8. **Variação de modelos** (até 10, tom suave/neutro/firme, cartão/simples), teste de todas as variações, relatório por modelo.
9. **Blindagem de arquivos:** `verificar_projeto.py`, `MANIFESTO.json`, workflow *Verificar arquivos*, pacote só com o que mudou.
10. **Desempenho e custo:** miniaturas, foto com pouca memória, importação sob demanda, consultas enxutas, cache, índices
    (`migracao_v6.sql`), limpeza opcional, câmera leve opcional, ping opcional, CSS de celular, este README.

---

## 16. Pendências e ideias

- Teste real da **bipagem** (lote de 1 ordem) e do **envio de WhatsApp** pelo gateway (chip dedicado).
- **Domínio próprio** para e-mail + SMTP de qualquer provedor + aquecimento automático das caixas.
- Ligar a **câmera leve** depois de testar no celular dos coletores.
- Arquivar fotos antigas de coletas já pagas se o armazenamento do Supabase se aproximar do limite.
- Fixar a versão do Streamlit no `requirements.txt` (ver tabela de problemas) quando o app estiver estável.
- Formatos de planilha da plataforma para atribuição em massa (distribuir pelo site e subir nas plataformas).
- 39 OS TIM com data de cancelamento ainda "Atribuído" para tratar.
