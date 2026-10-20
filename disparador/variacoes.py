"""Variação de modelos numa mesma campanha.

Cada destinatário recebe UM dos modelos escolhidos (até 10), distribuídos de forma embaralhada e proporcional aos pesos.
Os modelos variam em tom (suave / neutro / firme), assunto, texto e aparência (cartão ou simples), o que reduz o
risco de a campanha inteira ser tratada como spam e permite comparar qual funciona melhor.

Sem Streamlit e sem banco: a escolha de cada destinatário é guardada em `dados["_variante"]` (fila) ou calculada na hora.
"""
import random

MAX_VARIANTES = 10
TONS = ("suave", "neutro", "firme")
ROTULO_TOM = {"suave": "🟢 Suave", "neutro": "🟡 Neutro", "firme": "🔴 Firme"}

# Seis modelos prontos. Nenhum inventa prazo, multa ou ameaça: o tom muda só na forma de pedir.
PACOTE_PADRAO = [
    {"nome": "Lembrete amigável", "tom": "suave", "layout": "cartao",
     "assunto": "{nome}, vamos combinar a retirada do seu equipamento? (Protocolo {protocolo})",
     "texto": ("Tudo bem? Passando para combinar a retirada do roteador/modem que ficou com você "
               "(protocolo #{protocolo}). É rápido: basta confirmar o endereço abaixo pelo WhatsApp e a gente "
               "agenda o melhor horário para você."),
     "regras": "Se puder, deixe o roteador junto com a fonte. Se preferir, pode deixar na portaria do prédio."},
    {"nome": "Aviso de rota", "tom": "neutro", "layout": "cartao",
     "assunto": "Aviso de retirada de equipamento - Protocolo {protocolo}",
     "texto": ("Nossa equipe estará na sua região em breve para retirar o equipamento do protocolo #{protocolo}. "
               "Confirme se o endereço cadastrado está correto para evitarmos uma visita perdida."),
     "regras": "Deixe o roteador e a fonte separados. Se você mudou de endereço, informe pelo botão acima."},
    {"nome": "Confirmação rápida", "tom": "suave", "layout": "simples",
     "assunto": "Confirme seu endereço para a retirada - {protocolo}",
     "texto": ("Precisamos só de uma confirmação sua: o endereço abaixo ainda é o correto para retirarmos o "
               "equipamento do protocolo #{protocolo}? Responda pelo WhatsApp e já deixamos tudo agendado."),
     "regras": "Se a pessoa que atende mudou, pode avisar no WhatsApp também."},
    {"nome": "Devolução pendente", "tom": "neutro", "layout": "simples",
     "assunto": "Devolução de equipamento pendente - Protocolo {protocolo}",
     "texto": ("Consta no sistema uma devolução de equipamento pendente no protocolo #{protocolo}. "
               "Para finalizarmos a baixa, precisamos recolher o roteador/modem no endereço cadastrado."),
     "regras": "Deixe o equipamento com a fonte de energia. Pode ser entregue na portaria ou a alguém de confiança."},
    {"nome": "Providência necessária", "tom": "firme", "layout": "cartao",
     "assunto": "Importante: devolução do equipamento pendente - Protocolo {protocolo}",
     "texto": ("Este é um comunicado importante: o equipamento do protocolo #{protocolo} continua pendente de "
               "devolução e precisa ser recolhido. Pedimos que confirme o endereço pelo WhatsApp o quanto antes "
               "para que possamos agendar a retirada."),
     "regras": "É necessário que o roteador e a fonte estejam disponíveis para a retirada. Em apartamento, pode ficar na portaria."},
    {"nome": "Retirada obrigatória", "tom": "firme", "layout": "simples",
     "assunto": "Providência necessária: retirada do equipamento - Protocolo {protocolo}",
     "texto": ("Ainda não conseguimos recolher o equipamento vinculado ao protocolo #{protocolo}. A devolução é "
               "necessária para encerrar o seu cadastro. Responda agora pelo WhatsApp confirmando o endereço e "
               "providenciamos a retirada."),
     "regras": "Tenha em mãos o roteador e a fonte. Se não estiver em casa, deixe com alguém de confiança ou na portaria."},
]


def modelos_do_pacote():
    """Dicionário {rótulo: modelo} dos seis modelos prontos, no formato de modelo salvo (`tipo` = 'db')."""
    saida = {}
    for m in PACOTE_PADRAO:
        rotulo = f"[Pacote] {m['nome']} · {ROTULO_TOM[m['tom']]}"
        saida[rotulo] = {"tipo": "db", "nome": m["nome"], "assunto": m["assunto"], "texto": m["texto"],
                         "regras": m["regras"], "tom": m["tom"], "layout": m["layout"]}
    return saida


def tom_do_modelo(modelo):
    """Tom conhecido de um modelo (os padrões e os salvos sem tom contam como 'neutro')."""
    if modelo.get("tom") in TONS:
        return modelo["tom"]
    return "firme" if modelo.get("tipo") == "padrao1" else "neutro"


def e_multi(modelo):
    return isinstance(modelo, dict) and modelo.get("tipo") == "multi"


def montar_multi(variantes):
    """variantes: lista de {'rotulo', 'peso', 'modelo'} (1 a 10). Devolve o modelo composto guardado na campanha."""
    limpas = normalizar(variantes)
    if not limpas:
        raise ValueError("Escolha ao menos um modelo.")
    if len(limpas) > MAX_VARIANTES:
        raise ValueError(f"No máximo {MAX_VARIANTES} modelos por campanha.")
    return {"tipo": "multi", "variantes": limpas}


def normalizar(variantes):
    saida = []
    for i, v in enumerate(variantes or []):
        try:
            peso = float(v.get("peso", 1))
        except (TypeError, ValueError):
            peso = 1.0
        if peso <= 0:
            continue  # peso 0 = fora da campanha
        saida.append({"rotulo": str(v.get("rotulo") or f"Variação {i + 1}"), "peso": peso, "modelo": v["modelo"]})
    return saida


def da_campanha(modelo, nome_modelo):
    """Lista de variantes de uma campanha (um modelo simples vira lista de uma variante)."""
    if e_multi(modelo):
        return normalizar(modelo.get("variantes"))
    return [{"rotulo": nome_modelo, "peso": 1.0, "modelo": modelo}]


def atribuir(total, variantes, semente=None):
    """Lista com o índice da variante de cada posição: proporcional aos pesos, embaralhada e reproduzível."""
    n = len(variantes)
    if total <= 0:
        return []
    if n <= 1:
        return [0] * total
    soma = sum(v["peso"] for v in variantes)
    ideal = [total * v["peso"] / soma for v in variantes]
    cotas = [int(x) for x in ideal]
    sobras = sorted(range(n), key=lambda i: ideal[i] - cotas[i], reverse=True)
    for i in sobras[: total - sum(cotas)]:
        cotas[i] += 1
    lista = [i for i, c in enumerate(cotas) for _ in range(c)]
    random.Random(semente).shuffle(lista)
    return lista


def indice_da_linha(atribuicao, pos, n):
    """Índice válido da variante da posição `pos` (qualquer valor ausente/estranho cai numa variante existente)."""
    try:
        i = int(atribuicao[pos])
    except (TypeError, ValueError, IndexError):
        return pos % max(n, 1)
    return i if 0 <= i < n else pos % max(n, 1)
