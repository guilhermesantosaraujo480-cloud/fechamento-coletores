"""Fotos de comprovantes: validação, compactação, envio ao bucket privado e links temporários."""
import re
import urllib.parse
import uuid
from io import BytesIO

from .utils import agora_br

BUCKET = "comprovantes"
MARCADOR_PUBLICO = f"/object/public/{BUCKET}/"
TAMANHO_MAX_BYTES = 10 * 1024 * 1024


def processar_imagem(dados, lado_max=1280, qualidade=78):
    """Valida que é imagem de verdade, corrige a rotação do celular (EXIF) e compacta em JPEG."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(dados) > TAMANHO_MAX_BYTES:
        raise ValueError("A imagem é maior que 10 MB.")
    try:
        img = Image.open(BytesIO(dados))
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
    img.thumbnail((lado_max, lado_max))
    saida = BytesIO()
    img.save(saida, format="JPEG", quality=qualidade, optimize=True)
    return saida.getvalue()


def novo_caminho(prefixo):
    limpo = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(prefixo)).strip("_") or "arquivo"
    return f"{limpo}_{agora_br().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"


def ler_bytes(arquivo):
    """Aceita bytes, o arquivo do st.file_uploader ou qualquer objeto com read()."""
    if isinstance(arquivo, (bytes, bytearray)):
        return bytes(arquivo)
    return arquivo.getvalue() if hasattr(arquivo, "getvalue") else arquivo.read()


def salvar_foto(sb, arquivo, prefixo):
    """Envia a foto ao bucket e devolve só o CAMINHO (nunca uma URL pública)."""
    conteudo = processar_imagem(ler_bytes(arquivo))
    caminho = novo_caminho(prefixo)
    sb.storage.from_(BUCKET).upload(path=caminho, file=conteudo,
                                    file_options={"content-type": "image/jpeg"})
    return caminho


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
