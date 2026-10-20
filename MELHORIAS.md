# Melhorias do sistema

## Já feito
- **Segurança:** senhas com hash (bcrypt), sessão por token com hash, limite de tentativas de login, senhas de e-mail criptografadas
  (`CHAVE_CRIPTO`), comprovantes em bucket privado com link temporário, trilha de **Auditoria**.
- **Estrutura:** código separado em `core`, `ui`, `disparador`, `rotas` e `bipagem`, com testes automáticos.
- **Financeiro:** dinheiro em centavos, quinzenas, **saldo negativo levado para a quinzena seguinte**, ranking com *A pagar*,
  aparelhos acrescentados visíveis só na Visão geral/Coletas, edição na aprovação da coleta.
- **Rotas:** perfis Reintegra e CSS, vínculo por nome/apelido, tipos de coletor (normal, retentativa, depósito), avisos por OS,
  sugestão de coletor, fotografia diária com acompanhamento, coluna de WhatsApp do cliente, envio no grupo.
- **E-mails:** contas rotativas com limite diário, triagem (inválidos, duplicados, descadastrados, já enviados), versão em texto,
  `List-Unsubscribe`, contagem de cliques separando pessoas de robôs, IA gratuita só para rascunhos (você aprova).
- **Segundo plano:** fila no banco + GitHub Actions; pausar/retomar/cancelar; recuperação se o trabalhador cair.
- **Variação de modelos:** até 10 modelos por campanha, tom suave/neutro/firme, aparência cartão/simples, distribuição
  proporcional e embaralhada, teste de todas as variações, relatório por modelo.
- **Bipagem:** extração de OS/seriais do PDF, regra do ponto só quando necessário, agente local com Selenium, lotes pelo site.
- **Blindagem de arquivos:** `verificar_projeto.py` + verificação automática no GitHub (acusa arquivo vazio/trocado).

## Próximos passos sugeridos
1. **Domínio próprio** (`@rllogisticareversa.com.br`): 3 a 5 caixas, subdomínio só para campanhas, SPF/DKIM/DMARC.
   O disparador hoje fala com Gmail; ao contratar o e-mail, adaptar para SMTP de qualquer provedor.
2. **Aquecimento automático** das caixas novas (limite diário crescente por conta).
3. **Teste real da bipagem** com um lote de 1 ordem antes de usar em volume.
4. **Teste do envio de WhatsApp** pelo gateway (chip dedicado; gateways não oficiais podem ser banidos).
5. Usar o relatório por modelo para manter só as variações com mais cliques e menos descadastros.
