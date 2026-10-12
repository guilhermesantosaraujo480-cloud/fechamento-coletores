"""Textos enviados no WhatsApp."""
from core.utils import data_br

LIMITE_LEGENDA = 900  # WhatsApp aceita ~1024 caracteres na legenda de um arquivo


def resumo_bairros(can):
    return can.groupby(can["bairro"].replace("", "Sem bairro")).size().sort_values(ascending=False)


def mensagem_rota(empresa, coletor, data, can):
    bairros = resumo_bairros(can)
    linhas = [f"• {b}: {n}" for b, n in bairros.items()]
    cabecalho = (f"🚚 *ROTA {empresa.upper()}*\n📅 {data_br(data)}\n👷 *{coletor}*\n"
                 f"📦 *{len(can)}* coleta(s)\n\n📍 *Por bairro:*\n")
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
