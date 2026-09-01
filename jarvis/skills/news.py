"""Noticias por RSS (feedparser, sin API keys). Feeds en config.yaml."""

from __future__ import annotations

from jarvis.results import Rich

DEFAULT_FEEDS = {
    "El País": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
    "Xataka": "https://www.xataka.com/feedburner.xml",
}


def titulares(config: dict) -> Rich | str:
    import feedparser

    feeds = config.get("feeds") or DEFAULT_FEEDS
    lineas = []
    for fuente, url in feeds.items():
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:3]:
                lineas.append(f"• {entry.title}  ({fuente})")
        except Exception:
            continue
    if not lineas:
        return "No he podido leer las noticias (¿hay conexión?)."
    texto = "Titulares:\n" + "\n".join(lineas[:8])
    resumen = "Titulares: " + ". ".join(
        l.split("  (")[0].removeprefix("• ") for l in lineas[:3]
    )
    return Rich(texto, speak=resumen)
