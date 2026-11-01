
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"

FONTES_RSS = {
    "Hacker News": "https://news.ycombinator.com/rss",
    "GitHub Blog": "https://github.blog/feed/",
    "React Blog": "https://react.dev/rss.xml",
    "Python Insider": "https://blog.python.org/rss.xml",
}

LIMITE_POR_FONTE = 10


def baixar_xml(url):
    requisicao = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AgenteCuradoria/2.1",
            "Accept": (
                "application/rss+xml, "
                "application/atom+xml, "
                "application/xml, text/xml"
            ),
        },
    )

    with urllib.request.urlopen(
        requisicao,
        timeout=12,
    ) as resposta:
        conteudo = resposta.read(2_000_001)

    if len(conteudo) > 2_000_000:
        raise ValueError(
            "O arquivo XML excede o tamanho permitido."
        )

    return ET.fromstring(conteudo)


def limpar_texto(texto):
    return " ".join((texto or "").split())


def converter_data(valor):
    if not valor:
        return None

    try:
        data = parsedate_to_datetime(valor)

    except (TypeError, ValueError):
        try:
            data = datetime.fromisoformat(
                valor.replace("Z", "+00:00")
            )
        except ValueError:
            return None

    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)

    return data.astimezone(
        timezone.utc
    ).isoformat()


def ler_link_atom(entrada):
    for elemento in entrada.findall(
        f"{ATOM}link"
    ):
        relacao = elemento.get(
            "rel",
            "alternate",
        )

        if relacao == "alternate":
            return elemento.get("href", "")

    return entrada.findtext(
        f"{ATOM}id",
        default="",
    )


def buscar_rss(nome, url):
    raiz = baixar_xml(url)
    artigos = []

    entradas = raiz.findall(
        "./channel/item"
    )

    if entradas:
        for entrada in entradas[:LIMITE_POR_FONTE]:
            titulo = limpar_texto(
                entrada.findtext("title")
            )

            link = limpar_texto(
                entrada.findtext("link")
            )

            data = converter_data(
                entrada.findtext("pubDate")
            )

            if titulo and link.startswith(
                "https://"
            ):
                artigos.append({
                    "titulo": titulo,
                    "link": link,
                    "fonte": nome,
                    "data_publicacao": data,
                })

        return artigos

    entradas = raiz.findall(
        f"{ATOM}entry"
    )

    for entrada in entradas[:LIMITE_POR_FONTE]:
        titulo = limpar_texto(
            entrada.findtext(
                f"{ATOM}title"
            )
        )

        link = ler_link_atom(entrada)

        data = converter_data(
            entrada.findtext(
                f"{ATOM}published"
            )
            or entrada.findtext(
                f"{ATOM}updated"
            )
        )

        if titulo and link.startswith(
            "https://"
        ):
            artigos.append({
                "titulo": titulo,
                "link": link,
                "fonte": nome,
                "data_publicacao": data,
            })

    return artigos


def buscar_artigos(pergunta):
    parametros = urllib.parse.urlencode({
        "search_query": f"all:{pergunta}",
        "start": 0,
        "max_results": 10,
        "sortBy": "relevance",
    })

    url = (
        "https://export.arxiv.org/api/query?"
        f"{parametros}"
    )

    raiz = baixar_xml(url)
    artigos = []

    for entrada in raiz.findall(
        f"{ATOM}entry"
    ):
        titulo = limpar_texto(
            entrada.findtext(
                f"{ATOM}title"
            )
        )

        link = limpar_texto(
            entrada.findtext(
                f"{ATOM}id"
            )
        ).replace(
            "http://",
            "https://",
            1,
        )

        data = converter_data(
            entrada.findtext(
                f"{ATOM}published"
            )
        )

        if titulo and link.startswith(
            "https://"
        ):
            artigos.append({
                "titulo": titulo,
                "link": link,
                "fonte": "arXiv",
                "data_publicacao": data,
            })

    return artigos


def remover_duplicados(artigos):
    resultado = []
    links = set()

    for artigo in artigos:
        link = artigo["link"].rstrip("/")

        if link in links:
            continue

        links.add(link)
        resultado.append(artigo)

    return resultado


def ordenar_por_data(artigos):
    return sorted(
        artigos,
        key=lambda artigo: (
            artigo.get("data_publicacao") or ""
        ),
        reverse=True,
    )


def coletar_fontes(termo_arxiv):
    tarefas = {
        "arXiv": lambda: buscar_artigos(
            termo_arxiv
        )
    }

    for nome, url in FONTES_RSS.items():
        tarefas[nome] = (
            lambda nome=nome, url=url:
            buscar_rss(nome, url)
        )

    resultados = {}
    fontes_indisponiveis = []

    with ThreadPoolExecutor(
        max_workers=5
    ) as executor:
        futuros = {
            executor.submit(funcao): nome
            for nome, funcao in tarefas.items()
        }

        for futuro in as_completed(futuros):
            nome = futuros[futuro]

            try:
                resultados[nome] = (
                    futuro.result()
                )

            except Exception as erro:
                logger.warning(
                    "Falha na fonte %s: %s",
                    nome,
                    erro,
                )

                resultados[nome] = []
                fontes_indisponiveis.append(
                    nome
                )

    artigos = []

    for nome in tarefas:
        artigos.extend(
            resultados[nome][
                :LIMITE_POR_FONTE
            ]
        )

    artigos = remover_duplicados(
        artigos
    )

    return {
        "artigos": artigos,
        "fontes_indisponiveis": (
            fontes_indisponiveis
        ),
        "fontes_consultadas": list(
            tarefas
        ),
    }


def obter_feed():
    resultado = coletar_fontes(
        "machine learning"
    )

    artigos = ordenar_por_data(
        resultado["artigos"]
    )

    return {
        **resultado,
        "artigos": artigos,
        "total": len(artigos),
    }


def buscar_conteudos(pergunta):
    resultado = coletar_fontes(
        pergunta
    )

    termos = re.findall(
        r"\w+",
        pergunta.casefold(),
    )

    artigos = []

    for artigo in resultado["artigos"]:
        if artigo["fonte"] == "arXiv":
            artigos.append(artigo)
            continue

        titulo = artigo[
            "titulo"
        ].casefold()

        if termos and any(
            termo in titulo
            for termo in termos
        ):
            artigos.append(
                artigo
            )

    artigos = remover_duplicados(
        artigos
    )

    return {
        **resultado,
        "artigos": artigos,
    }
