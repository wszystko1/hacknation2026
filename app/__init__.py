"""ChrońPlon: ocena niedoboru wody działki."""
import mimetypes

# Na Windows Python bierze typy MIME z rejestru systemu, gdzie .js bywa text/plain (przeglądarka wtedy blokuje skrypt).
for _ext, _type in ((".js", "text/javascript"), (".css", "text/css"), (".woff2", "font/woff2"), (".svg", "image/svg+xml")):
    mimetypes.add_type(_type, _ext)
