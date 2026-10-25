"""Fotos de comprovantes: validação, compactação, envio ao bucket privado e links temporários."""
import re
import urllib.parse
import uuid
from io import BytesIO

from .utils import agora_br

BUCKET = "comprovantes"
MARCADOR_PUBLICO = f"/object/public/{BUCKET}/"
TAMANHO_MAX_BYTES = 10 * 1024 * 1024
LADO_MINIATURA = 320
SUFIXO_COM_MINIATURA = "_m.jpg"   # foto principal que TEM miniatura
SUFIXO_MINIATURA = "_t.jpg"


def _abrir_imagem(dados, lado_max):
    """Abre a imagem gastando pouca memória: em JPEG grande o Pillow decodifica já em tamanho reduzido (draft)."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(dados) > TAMANHO_MAX_BYTES:
        raise ValueError("A imagem é maior que 10 MB.")
    try:
        img = Image.open(BytesIO(dados))
        if img.format == "JPEG":
            img.draft("RGB", (lado_max * 2, lado_max * 2))  # decodifica em 1/2, 1/4 ou 1/8 do tamanho (bem menos memória)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as erro:
        raise ValueError("O arquivo enviado não é uma imagem válida.") from erro
    img = ImageOps.exif_transpose(img)  # foto de celular deitada volta a ficar em pé
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fundo = Image.new("RGB", img.size, (255, 255, 255))
        fundo.paste(img, mask=img.split()[-1])
        img = fundo
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _jpeg(img, lado, qualidade):
    img = img.copy()
    img.thumbnail((lado, lado))
    saida = BytesIO()
    img.save(saida, format="JPEG", quality=qualidade, optimize=True)
    return saida.getvalue()


def processar_imagem(dados, lado_max=1280, qualidade=78):
    """Valida que é imagem de verdade, corrige a rotação do celular (EXIF) e compacta em JPEG."""
    return _jpeg(_abrir_imagem(dados, lado_max), lado_max, qualidade)


def preparar_foto(dados, lado_max=1280, qualidade=78):
    """(foto_compacta, miniatura) a partir da foto original. A miniatura (~20 KB) serve para listas."""
    img = _abrir_imagem(dados, lado_max)
    return _jpeg(img, lado_max, qualidade), _jpeg(img, LADO_MINIATURA, 65)


def novo_caminho(prefixo):
    limpo = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(prefixo)).strip("_") or "arquivo"
    return f"{limpo}_{agora_br().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"


def caminho_miniatura(caminho):
    """Caminho da miniatura de uma foto nova (terminada em _m.jpg). Fotos antigas não têm: devolve None."""
    caminho = str(caminho or "")
    return caminho[: -len(SUFIXO_COM_MINIATURA)] + SUFIXO_MINIATURA if caminho.endswith(SUFIXO_COM_MINIATURA) else None


def ler_bytes(arquivo):
    """Aceita bytes, o arquivo do st.file_uploader ou qualquer objeto com read()."""
    if isinstance(arquivo, (bytes, bytearray)):
        return bytes(arquivo)
    return arquivo.getvalue() if hasattr(arquivo, "getvalue") else arquivo.read()


def enviar_foto_pronta(sb, principal, miniatura, prefixo):
    """Envia a foto já compactada (e a miniatura) e devolve só o CAMINHO. Se a miniatura falhar, a foto segue sem ela."""
    base = novo_caminho(prefixo)[:-4]
    opcoes = {"content-type": "image/jpeg"}
    caminho = base + ".jpg"
    if miniatura:
        try:
            sb.storage.from_(BUCKET).upload(path=base + SUFIXO_MINIATURA, file=miniatura, file_options=opcoes)
            caminho = base + SUFIXO_COM_MINIATURA  # o nome avisa que a miniatura existe
        except Exception:
            pass
    sb.storage.from_(BUCKET).upload(path=caminho, file=principal, file_options=opcoes)
    return caminho


def salvar_foto(sb, arquivo, prefixo):
    """Compacta a foto original, cria a miniatura e envia ao bucket privado. Devolve só o CAMINHO (nunca uma URL pública)."""
    principal, miniatura = preparar_foto(ler_bytes(arquivo))
    return enviar_foto_pronta(sb, principal, miniatura, prefixo)


def referencia_foto(valor):
    """Interpreta o que está salvo no banco. Devolve ('url', link) | ('caminho', arquivo) | (None, None).
    Aceita: caminho novo, URL pública antiga do Supabase e URLs externas."""
    if not valor:
        return None, None
    if isinstance(valor, dict):
        texto = valor.get("publicUrl") or valor.get("public_url") or ""
    else:
        texto = str(valor).strip()
    if not texto or texto.lower() in ("none", "null", "undefined", "nan"):
        return None, None
    if texto.startswith(("http://", "https://")):
        if MARCADOR_PUBLICO in texto:
            caminho = urllib.parse.unquote(texto.split(MARCADOR_PUBLICO, 1)[1].split("?")[0])
            return "caminho", caminho
        return "url", texto
    return "caminho", texto


def link_assinado(sb, caminho, segundos=3600):
    """Link temporário para um arquivo do bucket privado (None se falhar)."""
    try:
        res = sb.storage.from_(BUCKET).create_signed_url(caminho, segundos)
    except Exception:
        return None
    if isinstance(res, dict):
        return res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
    return None
