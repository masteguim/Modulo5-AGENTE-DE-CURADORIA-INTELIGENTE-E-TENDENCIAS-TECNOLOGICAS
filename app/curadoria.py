import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def buscar_artigos(pergunta: str) -> list[dict[str, str]]:
    parametros = urllib.parse.urlencode({
        "search_query": f"all:{pergunta}",
        "start": 0,
        "max_results": 5,
        "sortBy": "relevance",
    })

    url = f"https://export.arxiv.org/api/query?{parametros}"

    with urllib.request.urlopen(url, timeout=20) as resposta:
        raiz = ET.fromstring(resposta.read())

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    artigos = []

    for entrada in raiz.findall("atom:entry", namespace):
        titulo = entrada.findtext("atom:title", default="", namespaces=namespace)
        link = entrada.findtext("atom:id", default="", namespaces=namespace)

        artigos.append({
            "titulo": " ".join(titulo.split()),
            "link": link.replace("http://", "https://"),
        })

    return artigos