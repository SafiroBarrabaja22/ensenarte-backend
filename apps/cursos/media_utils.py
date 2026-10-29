from pathlib import Path
from urllib.parse import urlsplit


def url_archivo(archivo):
    if not archivo:
        return ""
    url = archivo.url
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith(("http://", "https://")):
        return url
    return f"/{url.lstrip('/')}"


def extension_archivo(archivo):
    if not archivo:
        return ""
    extension = Path(archivo.name or "").suffix
    if not extension:
        extension = Path(urlsplit(url_archivo(archivo)).path).suffix
    return extension.lower().lstrip(".")