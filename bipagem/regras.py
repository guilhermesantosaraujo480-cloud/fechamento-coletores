"""Regras puras da bipagem (sem navegador e sem banco)."""

# Tipos de aparelho do menu da plataforma: texto mostrado no site -> código digitado no seletor.
# Para acrescentar um tipo novo, basta incluir uma linha aqui.
EQUIPAMENTOS = {
    "002 HGU": "002",
    "001 IPTV": "001",
    "008 WIFI - 6": "008",
    "23 ADSL BASICO": "23",
}

# Quantos pontos no fim do serial, no máximo, antes de desistir da OS e pedir conferência manual.
MAX_PONTOS = 6


def codigo_do_equipamento(rotulo):
    """Código a digitar no seletor da plataforma (se o rótulo não estiver no menu, usa o próprio texto)."""
    return EQUIPAMENTOS.get(rotulo, str(rotulo).strip())


def pontos(serial):
    """Quantos pontos há no fim do serial."""
    s = str(serial)
    return len(s) - len(s.rstrip("."))


def mais_um_ponto(serial):
    """Serial já recusado como duplicado -> o mesmo serial com mais um ponto no fim."""
    return str(serial) + "."


def candidato(seriais, indice):
    """Serial da vez. A lista é usada em ordem; quando acaba, recomeça com um ponto no fim, depois dois..."""
    if not seriais:
        raise ValueError("Lista de seriais vazia.")
    n = len(seriais)
    return str(seriais[indice % n]) + "." * (indice // n)


class Pool:
    """Lista de seriais com um cursor. Só avança quando a plataforma aceitou o serial."""

    def __init__(self, seriais, indice=0):
        self.seriais = [str(s).strip() for s in seriais if str(s).strip()]
        if not self.seriais:
            raise ValueError("Lista de seriais vazia.")
        self.indice = int(indice)

    def atual(self):
        return candidato(self.seriais, self.indice)

    def consumir(self):
        self.indice += 1
