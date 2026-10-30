# Sistema de Coletas — Fechamento, Rotas, E-mails e Bipagem

Sistema interno (Streamlit + Supabase) da operação de recolhimento de equipamentos (Vivo/TIM), com as empresas
parceiras **Reintegra** e **CSS** e, para entrega de chips, a **Toolbox**. O **administrador** usa tudo; os **coletores** só enviam coletas, consultam o
próprio extrato e buscam comprovantes de clientes.

> **Regra de trabalho (definida pelo dono):** este README é o **diário do projeto**. A cada pedido, ler o README antes para saber
> em que pé estamos; a cada atualização, revisá-lo e registrar o que mudou **e as ideias novas** (seções 15 e 16), da forma mais
> específica possível. Nenhum pacote é entregue com o README desatualizado.
>
> **Para quem for alterar este projeto (inclusive o Claude):** leia primeiro as seções
> **"Regras que não podem quebrar"** e **"Histórico de mudanças"**. O dono do projeto pediu, em todas as rodadas:
> *"o que já funciona, não mexer"*. Mudanças novas devem ser **aditivas** e vir com testes.

Índice: 1 Visão geral · 2 Mapa dos arquivos · 3 Telas · 4 Regras que não podem quebrar · 5 Banco de dados ·
6 Configuração · 7 E-mails · 8 Rotas · 9 Bipagem · 10 Desempenho e custo · 11 Segurança · 12 Como atualizar ·
13 Testes · 14 Problemas conhecidos · 15 Histórico de mudanças · 16 Pendências · 17 Validação por pesquisa (o que vale e o que não vale)

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
  contato.py                Quem clicou -> telefone (fila ou planilha) -> link de WhatsApp com mensagem pronta
  ia.py                     Gemini grátis: só RASCUNHOS (humano aprova). Padrão `gemini-flash-latest`; se o modelo sumir (404), tenta o Flash atual
  sms.py                    SMS (regras puras): celular válido, texto sem acento, partes, frase "SAIR", triagem, janela de horário
  sms_gateway.py            Cliente da API do app "SMS Gateway for Android" (celular com o chip envia). Só biblioteca padrão
  sms_banco.py              Celulares, fila de SMS, histórico, estado de entrega, lista de SAIR (tabelas sms_*)
  sms_worker.py             Trabalhador do SMS (GitHub Actions): intervalo, limite diário por celular, horário, domingo, descadastro
  ui_sms.py                 Tela 📱 SMS: Enviar · Fila · Celulares · Sair · Histórico

rotas/                      Planilha da operadora -> rota por coletor -> WhatsApp (perfis Reintegra/CSS/Toolbox, nomes, avisos,
                            distribuição, acompanhamento, mensagens prontas, vinculos.telefone_do_coletor)
bipagem/                    PDF -> (OS, serial); regras do ponto; fila de lotes; motor; navegador Selenium; agente local
tests/                      Testes automáticos (fakes de Streamlit e Supabase em tests/fakes.py)
.github/workflows/          disparador.yml (e-mail + SMS a cada 30 min), sms.yml (acionar SMS na hora), verificar.yml (arquivos), manter_ativo.yml (ping opcional)
```

---

## 3. Telas

### Administrador (menu lateral)
| Tela | O que faz | Tabelas |
|---|---|---|
| 📊 Visão geral | Cards, ranking de coletores com **Saldo anterior** e **A pagar**, tabela de **acrescentados** (só aqui e em Coletas) | coletas, vales_coleta, premiacoes |
| 📋 Coletas | Pendentes (miniatura da foto, aprovar/recusar/**editar**), lançamentos do período (status/pago), "aprovar todas", "marcar pagas" | coletas |
| 💵 Fechamento | Por quinzena; vales; premiações; saldo negativo levado adiante; Excel; **📲 Enviar fechamento ao coletor** (abre o WhatsApp dele com o recibo, telefone de *Rotas → Coletores*) | coletas, vales_coleta, premiacoes |
| 📉 Vales / 🏅 Premiações | Lançar, ver comprovante (miniatura), excluir | vales_coleta, premiacoes |
| 🚚 Rotas | Gerar e enviar, Acompanhamento, Coletores, Empresas e grupos, Histórico | rota_* |
| 🔖 Bipagem | Novo lote (PDF/lista de seriais) e acompanhamento dos lotes | bipagem_* |
| 📧 E-mails | 🚀 Disparos · ⏱️ Fila · ✉️ Modelos · 🔑 Contas · 🚫 Descadastros · 📜 Histórico · 📈 Cliques · **📱 SMS** | campanhas, envios_email, sms_*... |
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
6. **Contato por WhatsApp só com quem clicou (pessoa), nunca com descadastrado**; sem telefone celular válido não há link.
7. **Não reenviar e-mail:** a triagem pula quem já está em `envios_email` (status enviado), descadastrados, inválidos e
   duplicados. `ja_enviados` filtrado por protocolo é equivalente ao completo; com protocolo vazio/estranho lê tudo.
8. **A IA só gera rascunho** de modelo. Nenhum modelo inventa multa, prazo ou ameaça; `VALOR_MULTA` só entra se configurado.
9. **Um trabalhador por vez** na fila (reserva `lease_ate` + `concurrency` no workflow). Envio interrompido volta para a fila.
10. **Bipagem:** o ponto `.` só é acrescentado ao serial quando a plataforma recusa por duplicidade (até 6 pontos); só avança o
   serial quando a plataforma aceita; depois de gravar dados parciais a OS vira "verificar" (nunca repete sozinha).
11. **Fotos nunca públicas:** guardar só o **caminho**; mostrar por link assinado temporário. Fotos novas têm nome `*_m.jpg`
    (com miniatura `*_t.jpg`); fotos antigas continuam funcionando sem miniatura.
12. **Segredos nunca no GitHub** (`.gitignore` bloqueia `secrets.toml` e `.env`).
13. **Arquivos nunca vazios:** `python verificar_projeto.py` e o GitHub conferem. Use "Upload files", não copie e cole.
14. **Mudança nova = aditiva + teste.** Telas que já funcionam não são reescritas sem pedido.
15. **Empresas já cadastradas (Reintegra e CSS) não mudam.** Empresa nova entra como perfil novo (ex.: Toolbox); um teste congela
    as colunas de entrada e saída dos dois perfis antigos.
16. **SMS:** só celular brasileiro; toda mensagem leva "Responda SAIR"; quem pediu para sair (SMS ou e-mail) nunca recebe; ritmo lento
    com intervalo aleatório, limite diário por celular, horário comercial e sem domingo por padrão; começar com poucos (~100).
17. **Os trabalhadores (e-mail e SMS) não podem importar o Streamlit** (o GitHub Actions não o instala): um teste confere isso.
18. **Nada é entregue ao dono antes do pedido** (pacote só quando ele pede; ideias e diagnósticos ficam só registrados aqui).

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
| `migracao_v7.sql` | **SMS** (sms_gateways, sms_campanhas, sms_destinos, sms_envios, sms_descadastros), `campanhas.agendada_para` (agendar e-mail), `cliques_chamados` ("já chamado"), `mensagens_rota` (mensagens prontas do WhatsApp das rotas) |

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
`WHATS_PROVEDOR`, `WHATS_API_URL`, `WHATS_API_KEY`, `WHATS_INSTANCIA`, `WHATS_CLIENT_TOKEN`, **`FOTO_LEVE`** (câmera leve; ver seção 10),
`GITHUB_WORKFLOW_SMS="sms.yml"` (opcional, para acionar o SMS na hora). O SMS reaproveita `EMPRESA_NOME`, `WHATSAPP_NUMERO`, `CHAVE_CRIPTO`.

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
**Agendar o início (ex.: 9h):** marque "🕘 Começar em horário marcado" ao colocar na fila (e-mail e SMS). Status "🕘 Agendada"; o trabalhador
confere a cada 30 min (pode começar até 30 min depois, a não ser que você acione na hora). Exige `migracao_v7.sql`.

**Ligação clique ↔ e-mail:** o botão do e-mail leva `envio=<envio_id>` para a Edge Function, que grava o clique em `cliques_email`. Se o
identificador gravado não for exatamente o `envio_id`, a aba Cliques liga por id do envio, protocolo ou e-mail (`metricas.ligar_aos_envios`)
e mostra o quadro **🩺 Diagnóstico da ligação** (quantos ligaram e por qual identificador). Cliques sem ligação nunca somem.

**"Já chamado":** na lista de quem clicou, marque quem você já chamou (tabela `cliques_chamados`); por padrão eles ficam escondidos.

**Chamar no WhatsApp quem clicou (📈 Cliques):** lista os clientes que clicaram (só **pessoas**, não robôs) com nome, protocolo (OS),
telefone e um link **💬 Enviar** que abre a conversa com a mensagem pronta e editável (`{cliente}`, `{protocolo}`, `{empresa}`).
O telefone vem da coluna Telefone/Celular da planilha: campanhas enviadas **pela Fila** o guardam em
`campanha_destinos.dados.telefone`; para campanhas antigas ou enviadas "agora, na tela", anexe a planilha original na própria
tela e o cruzamento é feito por protocolo + e-mail. Quem pediu para sair nunca aparece e telefone fixo não gera link.

### SMS pelo celular (aba 📧 E-mails → 📱 SMS)

**Ideia:** usar o **seu chip** (já validado) para mandar SMS curtos com o link do WhatsApp, pela mesma lógica da fila de e-mails.
O celular Android fica **ligado, com internet e no carregador**; um app grátis transforma o aparelho em "máquina de SMS" controlada pela
plataforma. Sem custo de SMS além do plano do chip.

**App a instalar no celular:** **SMS Gateway for Android™ (SMSGate)** — projeto de código aberto, site **sms-gate.app** (documentação em
docs.sms-gate.app). Instalação: pelo site (APK do GitHub *Releases*) — se o Google Play Protect bloquear, desative-o só durante a instalação.
Permissões: `SEND_SMS` (e `READ_PHONE_STATE` para escolher o chip). Android 5.0 ou mais novo. **Não funciona em iPhone.**

**Passo a passo (uma vez):**
1. Instale o app, permita o envio de SMS e **tire o app da economia de bateria** (senão o Android o "dorme").
2. Ligue **Cloud Server** e toque em **Offline** até virar **Online**; o app mostra **usuário** e **senha** da API.
3. Na plataforma: *E-mails → 📱 SMS → 📱 Celulares* → cadastre nome (ex.: "Chip Vivo 1"), usuário, senha, chip (1 ou 2) e **limite diário** (comece com 100) →
   **🔌 Testar conexão**. Mais de um chip/celular = cadastre cada um; a plataforma faz rodízio.
4. No app, em *Configurações → Mensagens*, confira intervalo entre mensagens, limite por hora/dia e horário de trabalho (valem junto com os da plataforma).
5. *✉️ Enviar*: suba a planilha (coluna Telefone/Celular), escolha 1 a 6 textos (ou escreva os seus), veja a **prévia** (contagem de caracteres e partes),
   envie o **SMS de teste** para o seu número, marque "Revisei" e **📥 Colocar na fila** (pode agendar o início).

**Como o envio funciona:** o trabalhador (`disparador.yml`, a cada 30 min, ou na hora pelo botão) manda cada SMS à API do app
(`POST https://api.sms-gate.app/3rdparty/v1/messages`, autenticação Basic com usuário/senha do app); o app envia pelo chip. Cada SMS espera
um intervalo aleatório (padrão 20–45 s). Se o celular estiver desligado, o pedido vence em 2 h (`ttl`) em vez de sair atrasado. Erros de
usuário/senha pausam a campanha; erro de um número só marca aquele número; erro temporário volta à fila; 5 erros seguidos pausam.
Em **📜 Histórico** o botão **🔄 Conferir entrega** pergunta ao app se cada SMS foi *Entregue* ou *Falhou* (coluna `estado`).

**Regras de proteção (padrão):** só celular brasileiro (fixo é ignorado) · **tirar acentos** (com acento o SMS cabe só 70 caracteres em vez de 160) ·
frase **"Responda SAIR p/ nao receber."** em todo SMS · lista **🚫 Sair** (cole os números de quem pediu; também vale quem está nos descadastros de e-mail) ·
não repete para o mesmo protocolo+telefone · horário 9h–19h e sem domingo (configurável) · limite diário por celular · alerta de texto em MAIÚSCULAS,
link encurtado ou mais de 2 partes. **A resposta "SAIR" ainda é lançada à mão** (webhook automático fica como melhoria).

**Riscos que continuam (pesquisa de 27/10/2026):** (1) operadora/celular pode bloquear a linha ou mandar para spam quem manda SMS parecido em
volume com link; por isso comece com poucos e use um chip que você aceite perder; (2) o app avisa que é para **baixo volume** e **uso legítimo**
(não campanhas de propaganda em massa) e recomenda ler os termos da operadora; (3) no **modo Cloud público**, texto e número passam pelo servidor do
app (HTTPS) e ele indica o modo só para dados não sensíveis — o app oferece criptografia ponta a ponta e **servidor privado** se quiser mais isolamento;
(4) o trabalhador dorme esperando o intervalo e usa minutos do GitHub Actions (≈ 30 s por SMS ⇒ 100 SMS ≈ 50 min; em repositório público é grátis, no privado
conta na cota) — se pesar, a alternativa é deixar o próprio app espaçar as mensagens.

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

**Toolbox (entrega de chips) — perfil `Toolbox (chips)`:** reconhecido sozinho pelas colunas `Pedido`, `Destino - Nome`, `Destino - Logradouro`,
`Descrição dos itens`. Lê o endereço das colunas **Destino** (as *Origem* são o armazém). A planilha de saída segue o modelo `ROTA_TIM.xlsx`
(`Pedido | Destino - Nome | CPF/CNPJ | Celular | Endereço Completo "RUA X N° 92" | Bairro | Cidade | CEP | UF | País | Informação adicional |
Descrição dos itens`), com celular e CEP **só números**, cidade em MAIÚSCULAS e ordem por cidade/bairro/CEP. A conferência avisa
**"Tipo do chip não é HLR nem NAKED"** e endereço com palavra repetida (`RUA RUA 4`). A mensagem do coletor traz o total `HLR: n · NAKED: m`.
Reintegra e CSS continuam exatamente como antes.

**Cadastrar nova empresa:** a tela agora sugere cada coluna ignorando `Destino - `/`Origem - ` (prefere *Destino*), aceita os campos opcionais
CPF/CNPJ, País e Descrição dos itens, e refaz as sugestões ao trocar a planilha de exemplo. (Corrigido o erro
`StreamlitDuplicateElementKey`: a chave `rp_nome` era usada duas vezes; agora é `rp_col_<campo>_<arquivo>`; há teste que recria o erro antigo.)

**Mensagem do link de WhatsApp:** lista de **mensagens prontas** (estou no endereço, chegando na região, confirmar endereço, entrega do chip,
não encontrei ninguém), mais as **suas**, salvas no banco (⭐). Campos: `{cliente}` `{coletor}` `{rua}` `{numero}` `{bairro}` `{cidade}` `{protocolo}`.
Campo vazio não deixa buraco ("Olá, , tudo bem?" vira "Olá, tudo bem?"). Mensagem curta = link curto. O padrão antigo continua igual.

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
Cobrem finanças, auth, fotos/miniaturas, e-mails (triagem, variações, fila, trabalhador, recuperação de queda), **SMS** (texto, API, fila, limites,
horário, descadastro, entrega), rotas (**Toolbox**, mensagens, nova empresa), fechamento por WhatsApp, IA (modelo desligado), cliques↔envios,
bipagem, telas (com Streamlit e Supabase simulados) e integridade dos arquivos (**o worker não importa o Streamlit**). Total: ~265 testes. **Limite:** o Streamlit simulado não
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
| SMS "Usuário ou senha incorretos/recusados" | (1) **Endereço da API** diferente de `https://api.sms-gate.app` (ex.: endereço do *Local server* com porta); (2) usuário/senha do bloco *Local server* em vez do *Cloud server*; (3) usuário/senha do app mudaram ou Cloud Server está Offline. A mensagem agora traz o código HTTP | Abrir o app, ligar Cloud Server (Online), recadastrar em 📱 Celulares e usar 🔌 Testar conexão |
| SMS fica "Pendente"/não sai | Celular desligado, sem internet ou o Android pôs o app para dormir | Carregador + internet + tirar o app da economia de bateria; ver o app |
| SMS pausou com "5 erros seguidos" | Celular fora, limite do app ou número recusado | Conferir o app; **▶️ Retomar** |
| Campanha de SMS não anda no domingo/à noite | Horário permitido (9h–19h, sem domingo) | Mudar na campanha ao criar (domingo/horas) |
| Cliques aparecem mas o desempenho por modelo é 0 | Identificador do clique ≠ envio_id (a Edge Function grava o protocolo) e coluna de data `data_clique` | Atualizado: aba Cliques liga por id/protocolo/e-mail; ver 🩺 Diagnóstico |
| IA de modelos dá "Modelo não encontrado" | `gemini-2.0-flash` foi desligado em 06/2026 | Já corrigido (padrão `gemini-flash-latest` + escolha automática); ou escolha um nome em "Ver modelos disponíveis" |
| Supabase "pausado" / app sem dados após dias parado | Plano gratuito pausa o projeto sem atividade por 7 dias | Restaurar no painel; o trabalhador agendado a cada 30 min já gera atividade |
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
11. **Correção da aba Cliques** (o filtro por período escondia cliques) e **lista "Chamar no WhatsApp quem clicou"**
    (coluna de telefone reconhecida na planilha, link `wa.me` com mensagem pronta).
12. **Ligação clique ↔ e-mail (26/10/2026, entregue no pacote completo de 27/10/2026):** no teste do dono havia 80 cliques de
    pessoas e 59 clientes, mas "Clicaram (pessoas)" por modelo = 0 e a lista de WhatsApp vazia: o identificador gravado no clique pela
    Edge Function não batia com o `envio_id` do e-mail. Agora `metricas.ligar_aos_envios` tenta `envio_id` (ignorando maiúsculas/espaços),
    id do envio, protocolo e e-mail, nessa ordem; clique sem ligação não some. Há um quadro "🩺 Diagnóstico da ligação" na aba Cliques
    (quantos ligaram, por qual identificador, colunas e exemplos). 3 testes novos (201 passando).
13. **SMS pelo celular (27/10/2026):** aba *E-mails → 📱 SMS* (Enviar · Fila · Celulares · Sair · Histórico), cliente do app **SMS Gateway for Android
    (SMSGate)**, trabalhador `sms_worker.py` (intervalo aleatório, limite diário por celular, horário 9h–19h, sem domingo, lista SAIR, recuperação
    de queda, pausa após 5 erros seguidos, 🔄 Conferir entrega), workflow `sms.yml`, tabelas `sms_*` (`migracao_v7.sql`). API conferida na
    documentação oficial em 27/10/2026 (`POST /3rdparty/v1/messages`, `GET /3rdparty/v1/messages/{id}`, `GET /3rdparty/v1/devices`).
14. **Agendamento de campanha (e-mail e SMS):** "🕘 Começar em horário marcado", status *Agendada* (coluna `campanhas.agendada_para`).
15. **Fechamento → WhatsApp:** botão "Enviar fechamento ao coletor" com o telefone de *Rotas → Coletores*; o texto **nunca** traz aparelhos
    acrescentados (regra 4, coberta por teste).
16. **"Já chamado"** na lista de quem clicou (`cliques_chamados`) e **mensagens prontas** do WhatsApp das rotas (`mensagens_rota`, campos
    `{rua}`, `{bairro}`, `{numero}`, `{protocolo}`, `{cliente}`, `{coletor}`...).
17. **Toolbox (TIM Blue Chip) e correção da tela "Cadastrar nova empresa":** perfil novo de entrega de chips (HLR/NAKED, saída igual ao
    `ROTA_TIM.xlsx`, ordenada por CEP, avisos de endereço suspeito e total HLR/NAKED por coletor); chaves dos campos renomeadas para
    `rp_col_<campo>` (fim do `StreamlitDuplicateElementKey`); sugestão de coluna ignora "Destino - "/"Origem - ". **Reintegra e CSS não mudaram**
    (teste confere). Revisão geral: ver seção 13 (≈ 265 testes) e a tabela de problemas (seção 14).
18. **Teste de conexão do SMS mais claro (29/10/2026):** o cliente do app tenta o **login por token (JWT)** quando o servidor recusa o login
    simples (401 **ou 403**) e as mensagens de erro agora mostram o **código HTTP** e a resposta do servidor. Motivo: no primeiro teste real
    o botão "🔌 Testar conexão" respondeu "Usuário ou senha incorretos" mesmo com os dados do Cloud server do app; sem como testar o servidor
    do app a partir do ambiente de desenvolvimento, passamos a mostrar o motivo real. 4 testes novos (`TestLoginPorToken`).
19. **Cliques e SMS, achados lendo o Supabase e o GitHub (30/10/2026):** (a) a tabela real `cliques_email` tem a coluna de data
    **`data_clique`** (o código só conhecia `data_hora`): por isso nenhum clique era visto como robô (80 "pessoas", 0 robôs) e o filtro de
    período caía no "tudo"; agora `data_clique` é reconhecida (robô por rajada e por clique logo após o envio voltam a funcionar);
    (b) a Edge Function `super-function` grava o **protocolo** em `cliques_email.envio_id` (ignora o parâmetro `envio`): a ligação por protocolo
    já cobre isso (82 de 84 cliques ligam) e foi coberta por teste; (c) SMS: o endereço da API cadastrado em alguns celulares estava errado
    (`…:443`, sem `https://`, `/mobile/v1`) e uma senha tinha tamanho de 16+ caracteres (provável caractere invisível colado); agora o endereço é
    normalizado para `https://api.sms-gate.app` e usuário/senha perdem espaços/caracteres invisíveis; (d) o GitHub tinha **arquivos soltos na raiz**
    (cópias de `campanha.py`, `fila.py`, `metricas.py`, `templates.py`, `ui.py`, `variacoes.py`, `worker.py`, `verificar.yml`, testes) por
    upload no lugar errado — são inofensivos mas podem ser apagados; e **faltavam** `migracao.sql`…`migracao_v6.sql` e `.env.exemplo`.
    **Sugestão (não aplicada):** trocar a Edge Function para gravar `envio_id: url.searchParams.get('envio') ?? protocolo` e guardar também o
    protocolo (coluna nova opcional) — a plataforma já aceita os dois formatos.
20. **Função de cliques atualizada direto no Supabase (29/10/2026, versão 3 da `super-function`; código em `supabase/super-function/redirect.ts`):**
    grava em `cliques_email.envio_id` o parâmetro `envio` do link (id do e-mail; sem ele, o protocolo, como antes), só redireciona para o
    WhatsApp (`wa.me`, `api.whatsapp.com`, `web.whatsapp.com`; antes qualquer endereço em `dest` era aceito, o que permitia usar o link do e-mail
    para levar o cliente a outro site), não decodifica a mensagem duas vezes (um `&` ou `#` no texto cortava a mensagem) e **sempre** redireciona
    mesmo se o banco falhar. Testada em Node com 8 verificações antes de publicar. Para voltar à versão antiga, publique de novo o código antigo
    (que só gravava `protocolo`). A plataforma aceita os dois formatos de clique.
    **Acesso do agente:** leitura do GitHub funciona; o envio de arquivos por lá exige instalar o *Claude GitHub App* no repositório
    (https://github.com/apps/claude/installations/select_target). Até lá, atualizações seguem por zip.
21. **Teste de conexão do SMS e erro 403 (29/10/2026):** no teste real o app respondeu **HTTP 403** (não 401) ao *listar celulares*. 403 = login
    reconhecido, mas sem permissão para essa consulta (a documentação do app usa o login simples só para **enviar**); 401 = usuário/senha
    errados. Agora o 🔌 Testar conexão trata 403 como "login aceito" e manda confirmar com o **SMS de teste** (aba ✉️ Enviar); 401 continua sendo erro.

---

## 16. Pendências e ideias

**Entregues no pacote completo de 27/10/2026 (itens 12 a 17 do histórico):** ligação clique↔e-mail, SMS, agendamento, fechamento por
WhatsApp, "já chamado", mensagens prontas, Toolbox e correção da tela de nova empresa. Antes de usar: rodar `migracao_v7.sql` no Supabase.

**Ainda em aberto (de propósito):**
- **Conferir com cliques novos** o quadro 🩺 Diagnóstico (por qual identificador o clique ligou). Se aparecer "sem ligação", ajustar a Edge
  Function do Supabase para gravar o parâmetro `envio` do link em `cliques_email.envio_id`.
- **Teste do link limpo no Circuit** (4 formatos de coluna WhatsApp; ver abaixo). Só será gerado quando o dono pedir.
- **Resposta "SAIR" do SMS automática** (hoje a lista de SAIR é preenchida à mão; o app permite webhook de SMS recebido).
- **Primeiro envio de SMS real:** começar com ~10, depois ~100, em chip que possa ser perdido; acompanhar entrega em 📜 Histórico.
- **Janela de envio do e-mail** (ex.: só 8h–18h) — o SMS já tem horário permitido; o e-mail ainda não.
- **Toolbox é uma empresa de ENTREGA DE CHIPS (não de retirada de equipamentos)** — informado pelo dono em 26/10/2026. A lógica da
  planilha de rota é um pouco diferente das de coleta: leva o **tipo de chip (HLR ou NAKED)**, que é importante e vem da coluna
  **"Descrição dos itens"** da exportação (223 linhas de exemplo: 114 HLR e 109 NAKED). O dono montou à mão um **modelo de saída**
  (`ROTA_TIM.xlsx`, aba `orders`, 40 pedidos de Suzano e Mogi das Cruzes, **ordenado por CEP**) com as colunas, nesta ordem:
  `Pedido | Destino - Nome | Destino - CPF/CNPJ | Destino - Celular | Endereço Completo | Destino - Bairro | Destino - Cidade |
  Destino - CEP | Destino - UF | Destino - País | Destino - Informação adicional | Descrição dos itens (HLR/NAKED)`.
  O "Endereço Completo" segue o formato `RUA X N° 92` (logradouro + "N°" + número). Observações para a implementação: padronizar a
  cidade (aparece "SUZANO" e "Suzano"); sinalizar endereços suspeitos como `RUA RUA L N° 265` e `RUA MIGUEL LOPES DE N° OLIVEIRA`
  (número digitado como nome); considerar total de HLR x NAKED por coletor no resumo/WhatsApp. Esta empresa precisará de um perfil
  de saída próprio (CPF e chip não existem nos perfis atuais). O dono avisou que vai mandar mais modelos.
- **Nova empresa "Toolbox/TIM Blue Chip" (planilha `pedidos (9).xlsx`):** é uma exportação de **entregas** ("Entrega em Lote", canal
  "Toutbox - Webhook", conta "Rotalog - TIM Blue Chip", status "Não Processado", sem Transportador). O endereço do cliente está nas colunas
  **"Destino - ..."** (as "Origem - ..." são o armazém TIM: TCO/TSP/TMG...). Há linhas de teste ("NOME DE TESTE"). Mapeamento
  previsto: Pedido = protocolo, Destino - Nome, Destino - Logradouro/Número/Bairro/Cidade/CEP/UF, Destino - Celular e Telefone,
  Destino - Informação adicional = complemento; extras: Transportador = coletor, Voluntário?, Agendamento para até, Status de Agendamento,
  Tentativas, Prioridade, Reaberto em.
- **Regra para empresas novas (26/10/2026):** as empresas já cadastradas (Reintegra, CSS) estão perfeitas e **não podem ser alteradas**;
  a Toolbox entra como perfil novo, revisando tudo para que uma coisa não atrapalhe a outra. O objetivo do dono com a Toolbox é só
  **montar a planilha e mandar** para os entregadores.
- **Como o dono opera hoje:** o envio automático de WhatsApp (gateway pago) **não está ativado** — fica disponível para ativar se
  ele quiser. Ele gera as planilhas, baixa o **zip** e manda manualmente aos coletores, que importam a rota no roteirizador
  **Circuit (Spoke)**. A coluna **WhatsApp** (link `wa.me`) na planilha funciona perfeitamente.
- **Link do WhatsApp muito grande (dúvida respondida em 26/10/2026):** o tamanho vem da mensagem codificada (~167 caracteres com a
  mensagem padrão; ~96 com uma mensagem curta; ~27 só com o número, `https://wa.me/55DDDNUMERO`). Opções: (1) mensagem mais curta;
  (2) opção **"link curto" sem mensagem** (o coletor abre a conversa e escreve); (3) texto amigável no lugar da URL ("Enviar WhatsApp")
  **só se o Circuit aceitar** — ele provavelmente importa o texto da célula e não o endereço escondido do hiperlink, então testar com
  uma planilha de 3 linhas antes; (4) redirecionador próprio (Edge Function do Supabase) gerando `.../go/AbC12` — mais trabalho e
  depende do banco. Encurtadores de terceiros (bit.ly etc.) não são recomendados: dependência externa e telefones dos clientes saem do sistema.
- **Esclarecimento do dono (26/10/2026):** o incômodo não é o tamanho da mensagem, e sim o **texto gigante da URL aparecendo no app do
  coletor (Circuit)**. Ele quer algo mais limpo/intuitivo (ex.: "Enviar WhatsApp" / "Ver mapa") que continue **clicável** no Circuit.
  Depende de o Circuit reconhecer o link. **Plano de teste combinado (a gerar só quando o dono pedir):** planilha pequena com 4 linhas
  usando formatos diferentes na coluna — (a) URL pura (como hoje), (b) URL curta sem mensagem (`wa.me/55...`), (c) hiperlink do Excel
  com texto amigável, (d) fórmula `=HYPERLINK(url;"Enviar WhatsApp")` — para ver no Circuit qual aparece limpo e abre ao tocar.
  O padrão atual (URL pura) não pode ser trocado antes desse teste.
- **Decisão do dono (26/10/2026):** a **mensagem pronta dentro do link é essencial** (o coletor clica e a frase já vai para o cliente,
  ganhando tempo). Por isso a opção "link curto sem mensagem" foi **descartada**. Ficam: (1) texto amigável clicável ("Enviar WhatsApp" /
  "Ver mapa") **se o Circuit aceitar** (teste acima); (2) se não aceitar, **redirecionador próprio** (link curto que guarda a mensagem
  e redireciona para o `wa.me`; usaria a Edge Function do Supabase já existente + tabela de códigos; o endereço continua longo-ish,
  ~60-70 caracteres, mas bem menor que ~167); (3) manter como está (os coletores já estão acostumados). O dono disse que, se não
  houver jeito, **não tem problema** — é só praticidade.
- **Ideia para a próxima atualização — modelos de mensagem do link de WhatsApp (Rotas):** biblioteca de mensagens prontas para
  **selecionar** (ex.: "Estamos próximos ao seu endereço", "Bom dia, meu nome é {coletor}...") em vez de digitar toda vez, com
  **mais campos** para inserir na mensagem: hoje existem `{cliente}` e `{coletor}`; incluir `{rua}`, `{bairro}`, `{numero}`,
  `{protocolo}`, etc. Mensagens salvas no banco (tabela nova) e escolhidas na hora de gerar a rota. Mensagem mais curta = link mais curto.
- **Ideia (26/10/2026) — disparo de SMS com o chip próprio** (vários números, mensagem curta com o link do WhatsApp). Implementada em 27/10/2026 (ver seção 7).
  Parecer dado na época: viável, mas com risco de a operadora bloquear a linha e de o link ser tratado como spam. Caminhos: (a) celular Android
  como gateway de SMS ligado à fila (ritmo lento, limite diário por chip, rodízio entre os chips, "responda SAIR", reaproveitando
  descadastros e variações de texto); (b) API de SMS paga (remetente registrado, melhor entrega); (c) sem automação: link `sms:` na lista
  de quem clicou/não respondeu, um toque por cliente. Recomendado começar por teste pequeno. Nada implementado.

**Avaliação de plataforma (resposta dada em 26/10/2026):** manter **Python/Streamlit**. Ele não está no limite para uso interno de
um administrador; os limites reais são o plano gratuito (o app dorme, ~1 GB de memória) e o celular dos coletores. Reescrever em
JavaScript/Java/PHP custaria meses sem ganho funcional, porque a lógica (`core`, `disparador`, `rotas`, `bipagem`) é Python testado.
Caminho incremental se o uso crescer: (1) hospedagem paga barata que não dorme; (2) só a **tela do coletor** vira um site/PWA
leve falando direto com o Supabase, e o administrador continua no Streamlit; (3) só então pensar em API própria (FastAPI) + front-end.

**Antigas:**
- Teste real da **bipagem** (lote de 1 ordem) e do **envio de WhatsApp** pelo gateway (chip dedicado).
- **Domínio próprio** para e-mail + SMTP de qualquer provedor + aquecimento automático das caixas.
- Ligar a **câmera leve** depois de testar no celular dos coletores.
- Arquivar fotos antigas de coletas já pagas se o armazenamento do Supabase se aproximar do limite.
- Fixar a versão do Streamlit no `requirements.txt` (ver tabela de problemas) quando o app estiver estável.
- Formatos de planilha da plataforma para atribuição em massa (distribuir pelo site e subir nas plataformas).
- 39 OS TIM com data de cancelamento ainda "Atribuído" para tratar.
