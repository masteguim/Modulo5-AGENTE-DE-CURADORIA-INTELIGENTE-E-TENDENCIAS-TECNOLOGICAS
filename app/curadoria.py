import logging
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

logger = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"

FONTES_RSS = {
    "Hacker News": "https://news.ycombinator.com/rss",
    "GitHub Blog": "https://github.blog/feed/",
    "React Blog": "https://react.dev/rss.xml",
    "Python Insider": "https://blog.python.org/rss.xml",
}

LIMITE_POR_FONTE = 10
LIMITE_RECOMENDACOES = 5

PALAVRAS_IGNORADAS = {
    "a", "as", "o", "os", "de", "do", "da", "dos",
    "das", "um", "uma", "uns", "umas", "em",
    "no", "na", "nos", "nas", "para", "por",
    "com", "sobre", "quais", "qual", "sao",
    "que", "como", "me", "mostre", "artigos",
    "noticias", "novidades", "recentes",
    "the", "and", "for", "with", "about",
    "from", "what", "are", "new", "latest",
}


def baixar_xml(url):
    requisicao = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AgenteCuradoria/2.2",
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
            "O XML excede o tamanho permitido."
        )

    return ET.fromstring(conteudo)


def limpar_texto(texto):
    texto = unescape(texto or "")
    texto = re.sub(r"<[^>]+>", " ", texto)

    return " ".join(texto.split())


def normalizar_texto(texto):
    texto = unicodedata.normalize(
        "NFKD",
        limpar_texto(texto),
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    return texto.casefold()


def extrair_termos(pergunta):
    palavras = re.findall(
        r"[a-z0-9+#.]+",
        normalizar_texto(pergunta),
    )

    return list(dict.fromkeys(
        palavra
        for palavra in palavras
        if palavra not in PALAVRAS_IGNORADAS
        and len(palavra) >= 2
    ))


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
        if elemento.get("rel", "alternate") == "alternate":
            return elemento.get("href", "")

    return entrada.findtext(
        f"{ATOM}id",
        default="",
    )


def criar_artigo(
    titulo,
    link,
    fonte,
    data_publicacao=None,
    resumo="",
):
    titulo = limpar_texto(titulo)
    link = (link or "").strip()

    if not titulo or not link.startswith("https://"):
        return None

    return {
        "titulo": titulo,
        "link": link,
        "fonte": fonte,
        "data_publicacao": data_publicacao,
        "resumo": limpar_texto(resumo),
    }


def buscar_rss(nome, url):
    raiz = baixar_xml(url)
    artigos = []

    entradas_rss = raiz.findall("./channel/item")

    if entradas_rss:
        for entrada in entradas_rss[:LIMITE_POR_FONTE]:
            artigo = criar_artigo(
                titulo=entrada.findtext("title"),
                link=entrada.findtext("link"),
                fonte=nome,
                data_publicacao=converter_data(
                    entrada.findtext("pubDate")
                ),
                resumo=entrada.findtext("description", ""),
            )

            if artigo:
                artigos.append(artigo)

        return artigos

    entradas_atom = raiz.findall(
        f"{ATOM}entry"
    )

    for entrada in entradas_atom[:LIMITE_POR_FONTE]:
        artigo = criar_artigo(
            titulo=entrada.findtext(f"{ATOM}title"),
            link=ler_link_atom(entrada),
            fonte=nome,
            data_publicacao=converter_data(
                entrada.findtext(f"{ATOM}published")
                or entrada.findtext(f"{ATOM}updated")
            ),
            resumo=(
                entrada.findtext(f"{ATOM}summary")
                or entrada.findtext(f"{ATOM}content")
                or ""
            ),
        )

        if artigo:
            artigos.append(artigo)

    return artigos


def buscar_artigos(pergunta):
    parametros = urllib.parse.urlencode({
        "search_query": f"all:{pergunta}",
        "start": 0,
        "max_results": LIMITE_POR_FONTE,
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
        link = (
            entrada.findtext(f"{ATOM}id", default="")
            .replace("http://", "https://", 1)
        )

        artigo = criar_artigo(
            titulo=entrada.findtext(f"{ATOM}title"),
            link=link,
            fonte="arXiv",
            data_publicacao=converter_data(
                entrada.findtext(f"{ATOM}published")
            ),
            resumo=entrada.findtext(
                f"{ATOM}summary",
                default="",
            ),
        )

        if artigo:
            artigos.append(artigo)

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
    indisponiveis = []

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
                resultados[nome] = futuro.result()

            except Exception as erro:
                logger.warning(
                    "Falha ao consultar %s: %s",
                    nome,
                    erro,
                )

                resultados[nome] = []
                indisponiveis.append(nome)

    artigos = []

    for nome in tarefas:
        artigos.extend(
            resultados[nome][:LIMITE_POR_FONTE]
        )

    return {
        "artigos": remover_duplicados(artigos),
        "fontes_consultadas": list(tarefas),
        "fontes_indisponiveis": indisponiveis,
    }


def calcular_relevancia(artigo, termos):
    if not termos:
        return 0

    titulo = normalizar_texto(
        artigo["titulo"]
    )

    resumo = normalizar_texto(
        artigo.get("resumo", "")
    )

    pontos = 0

    for termo in termos:
        padrao = (
            r"(?<!\w)"
            + re.escape(termo)
            + r"(?!\w)"
        )

        if re.search(padrao, titulo):
            pontos += 3

        elif re.search(padrao, resumo):
            pontos += 1

    return pontos


def selecionar_recomendacoes(artigos, pergunta):
    termos = extrair_termos(pergunta)

    artigos_rss = []
    artigos_arxiv = []

    for artigo in artigos:
        if artigo["fonte"] == "arXiv":
            artigos_arxiv.append(artigo)
            continue

        pontuacao = calcular_relevancia(
            artigo,
            termos,
        )

        if pontuacao > 0:
            artigos_rss.append({
                **artigo,
                "_pontuacao": pontuacao,
            })

    artigos_rss.sort(
        key=lambda artigo: (
            artigo["_pontuacao"],
            artigo.get("data_publicacao") or "",
        ),
        reverse=True,
    )

    grupos = defaultdict(list)

    for artigo in artigos_rss:
        grupos[artigo["fonte"]].append(artigo)

    selecionados = []
    links = set()

    def adicionar(artigo):
        if len(selecionados) >= LIMITE_RECOMENDACOES:
            return False

        link = artigo["link"]

        if link in links:
            return False

        selecionados.append(artigo)
        links.add(link)

        return True

    if grupos:
        limite_rss = 3

        while len(selecionados) < limite_rss:
            adicionou = False

            for fonte in list(grupos):
                if len(selecionados) >= limite_rss:
                    break

                if grupos[fonte]:
                    artigo = grupos[fonte].pop(0)
                    adicionou = adicionar(artigo) or adicionou

            if not adicionou:
                break

    for artigo in artigos_arxiv:
        adicionar(artigo)

    if len(selecionados) < LIMITE_RECOMENDACOES:
        restantes = sorted(
            (
                artigo
                for grupo in grupos.values()
                for artigo in grupo
            ),
            key=lambda artigo: (
                artigo["_pontuacao"],
                artigo.get("data_publicacao") or "",
            ),
            reverse=True,
        )

        for artigo in restantes:
            adicionar(artigo)

    return [
        {
            chave: valor
            for chave, valor in artigo.items()
            if not chave.startswith("_")
        }
        for artigo in selecionados
    ]


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
    resultado = coletar_fontes(pergunta)

    artigos = selecionar_recomendacoes(
        resultado["artigos"],
        pergunta,
    )

    return {
        **resultado,
        "artigos": artigos,
    }
