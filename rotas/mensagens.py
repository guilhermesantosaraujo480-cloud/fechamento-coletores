"""Textos enviados no WhatsApp."""
from core.utils import data_br

from . import avisos as av

LIMITE_LEGENDA = 900  # WhatsApp aceita ~1024 caracteres na legenda de um arquivo


def resumo_bairros(can):
    """Quantidade por bairro (bairro genérico aparece como 'CEP 08485-xxx')."""
    rotulo = {}
    for ef, raw in zip(can["bairro_ef"], can["bairro"]):
        if ef in rotulo:
            continue
        if ef.startswith("CEP "):
            rotulo[ef] = f"Região do {ef}"
        elif ef.startswith("SEM "):
            rotulo[ef] = "Sem bairro"
        else:
            rotulo[ef] = raw or ef.title()
    return can["bairro_ef"].map(rotulo).value_counts()


def mensagem_rota(empresa, coletor, data, can):
    bairros = resumo_bairros(can)
    linhas = [f"• {b}: {n}" for b, n in bairros.items()]
    destaque = av.linha_resumo(av.contagem(can)) if "avisos" in can else ""
    cabecalho = (f"🚚 *ROTA {empresa.upper()}*\n📅 {data_br(data)}\n👷 *{coletor}*\n"
                 f"📦 *{len(can)}* coleta(s)\n" + (f"{destaque}\n" if destaque else "") + "\n📍 *Por bairro:*\n")
    rodape = "\n\n📎 Planilha completa com endereços, telefones e links do mapa no arquivo."
    texto = cabecalho + "\n".join(linhas) + rodape
    while len(texto) > LIMITE_LEGENDA and len(linhas) > 3:
        linhas = linhas[:-1]
        texto = cabecalho + "\n".join(linhas) + f"\n… e mais {len(bairros) - len(linhas)} bairro(s)" + rodape
    return texto


def lista_para_copiar(empresa, coletor, data, can, limite=3500):
    """Versão em texto com todas as paradas (para quando não há gateway de envio)."""
    linhas = [f"*ROTA {empresa.upper()}* — {data_br(data)} — *{coletor}* ({len(can)} coletas)\n"]
    for i, r in enumerate(can.itertuples(), 1):
        tel = f" ☎ {r.telefone}" if r.telefone else ""
        linhas.append(f"{i}) {r.nome} — {r.endereco_completo}, {r.bairro}{tel}")
    texto = "\n".join(linhas)
    return texto if len(texto) <= limite else texto[:limite].rsplit("\n", 1)[0] + "\n… (lista completa na planilha)"
