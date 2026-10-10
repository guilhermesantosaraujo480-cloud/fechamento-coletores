# Melhorias desta versão

## Erros corrigidos
- Coletas **pendentes sumiam** quando a data estava fora do filtro: agora aparecem sempre.
- Totais cortados em **1000 linhas** (limite do Supabase): consultas paginadas e filtradas por período no servidor.
- `st.tabs` executava **todas as abas a cada clique** (inclusive consultas pesadas de cliques): navegação agora desenha só a seção aberta.
- `usuarios.select("*")` colocava **hashes de senha em cache**: agora só colunas públicas.
- Foto de celular **deitada** (EXIF): corrigida na compactação; arquivos que não são imagem são recusados.
- Busca de comprovantes quebrava com data inválida e **registrava log a cada rerun**: agora uma vez por termo.
- `except: pass` escondia falhas (limite diário de e-mails ignorado se a leitura falhasse): erros agora aparecem.
- Valores em **float** e formato `R$ 1234.50`: cálculo em centavos e formato brasileiro `R$ 1.234,50`.
- Dois administradores aprovando a mesma coleta: a decisão só vale se ainda estiver pendente.
- Pagamento marcado em coleta recusada: ignorado.
- Botão PARAR do disparo perdia o relatório: agora o resultado parcial fica salvo.
- Planilha de clientes com `=` no início virava fórmula no Excel: neutralizado.

## Arquitetura
- Código dividido em `core/`, `ui/` e `disparador/` (módulos pequenos, regras separadas da tela).
- 51 testes automatizados.

## Layout
- Tela larga, menu lateral (admin) e menu superior (coletor, celular).
- Filtros globais: Hoje, 7 dias, 30 dias, Este mês, Mês passado, Personalizado + coletor.
- Visão geral com 8 indicadores, gráfico por dia e ranking.
- Pendentes em cartões com foto; tabela editável para corrigir status/pago (dá para desfazer).
- Vales e premiações: formulário ao lado do histórico; exclusão de lançamento errado.
- Selo de pendências na barra lateral.

## Segurança e administração
- Trocar a própria senha; redefinir senha, desativar e encerrar sessões de usuários.
- Revalidação periódica da sessão (usuário desativado é desconectado).
- Trilha de auditoria; login com validação (3–30 caracteres), senha mínima de 6.
- Nome de coletor duplicado é bloqueado (coletas são ligadas ao nome).

## Disparador
- Colunas da planilha reconhecidas automaticamente (aceita acentos e variações) e ajustáveis.
- Relatório antes do envio: quantos recebem e por que os outros são pulados.
- Cliques: separa pessoas de robôs; taxa real de clique.
- IA: mensagens de erro claras e botão "Ver modelos disponíveis".

## Recomendações futuras
- Ligar coletas ao `id` do usuário (hoje é pelo nome).
- Uma sessão por aparelho (hoje, entrar em outro aparelho derruba o primeiro).
- Rotacionar a chave Gemini que foi colada no chat; ativar RLS (PASSOS 2 e 3 do `migracao.sql`) com a `service_role`.
