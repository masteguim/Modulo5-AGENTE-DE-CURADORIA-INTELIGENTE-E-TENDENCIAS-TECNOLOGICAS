
import logging
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape

logger = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"

FONTES_RSS = {
    "Tecnoblog": {
        "url": "https://tecnoblog.net/feed/",
        "idioma": "pt",
    },
    "Olhar Digital": {
        "url": "https://olhardigital.com.br/feed/",
        "idioma": "pt",
    },
    "Hacker News": {
        "url": "https://news.ycombinator.com/rss",
        "idioma": "en",
    },
    "GitHub Blog": {
        "url": "https://github.blog/feed/",
        "idioma": "en",
    },
    "React Blog": {
        "url": "https://react.dev/rss.xml",
        "idioma": "en",
    },
    "Python Insider": {
        "url": "https://blog.python.org/rss.xml",
        "idioma": "en",
    },
}

LIMITE_POR_FONTE = 10
LIMITE_RECOMENDACOES = 5

IGNORADAS = {
    "a", "as", "o", "os", "de", "da", "do",
    "das", "dos", "em", "um", "uma", "para",
    "com", "sobre", "quais", "qual", "que",
    "como", "sao", "me", "mostre", "artigos",
    "noticias", "novidades", "recentes",
    "the", "and", "for", "from", "about",
    "what", "with", "latest", "news",
}

TRADUCOES = {
    "inteligencia": ["intelligence"],
    "artificial": ["artificial"],
    "seguranca": ["security"],
    "programacao": ["programming"],
    "desenvolvimento": ["development"],
    "software": ["software"],
    "computacao": ["computing"],
    "quantica": ["quantum"],
    "aprendizado": ["learning"],
    "maquina": ["machine"],
    "dados": ["data"],
    "vulnerabilidade": ["vulnerability"],
    "vulnerabilidades": ["vulnerabilities"],
}


def limpar_texto(texto):
    texto = unescape(texto or "")
    texto = re.sub(r"<[^>]+>", " ", texto)
    return " ".join(texto.split())


def normalizar(texto):
    texto = unicodedata.normalize(
        "NFKD", limpar_texto(texto)
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
        normalizar(pergunta),
    )

    termos = []

    for palavra in palavras:
        if palavra in IGNORADAS or len(palavra) < 2:
            continue

        termos.append(palavra)
        termos.extend(TRADUCOES.get(palavra, []))

    return list(dict.fromkeys(termos))


def baixar_xml(url):
    requisicao = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AgenteCuradoria/2.3",
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


def converter_data(valor):
    if not valor:
        return None

    try:
        data = parsedate_to_datetime(valor)

    except (TypeError, ValueError):
        try:
            data = datetime.fromisoformat(valor)

        except (TypeError, ValueError):
            return None

    if data.tzinfo is None:
        data = data.replace(tzinfo=UTC)

    return data.astimezone(UTC).isoformat()


def criar_artigo(
    titulo,
    link,
    fonte,
    idioma,
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
        "idioma": idioma,
        "data_publicacao": data_publicacao,
        "resumo": limpar_texto(resumo),
    }


def ler_link_atom(entrada):
    for elemento in entrada.findall(f"{ATOM}link"):
        if elemento.get("rel", "alternate") == "alternate":
            return elemento.get("href", "")

    return entrada.findtext(
        f"{ATOM}id",
        default="",
    )


def buscar_rss(nome, configuracao):
    raiz = baixar_xml(configuracao["url"])
    idioma = configuracao["idioma"]
    artigos = []

    entradas = raiz.findall("./channel/item")

    if entradas:
        for entrada in entradas[:LIMITE_POR_FONTE]:
            artigo = criar_artigo(
                titulo=entrada.findtext("title"),
                link=entrada.findtext("link"),
                fonte=nome,
                idioma=idioma,
                data_publicacao=converter_data(
                    entrada.findtext("pubDate")
                ),
                resumo=(
                    entrada.findtext("description")
                    or entrada.findtext(f"{CONTENT}encoded")
                    or ""
                ),
            )

            if artigo:
                artigos.append(artigo)

        return artigos

    entradas = raiz.findall(f"{ATOM}entry")

    for entrada in entradas[:LIMITE_POR_FONTE]:
        artigo = criar_artigo(
            titulo=entrada.findtext(f"{ATOM}title"),
            link=ler_link_atom(entrada),
            fonte=nome,
            idioma=idioma,
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

    for entrada in raiz.findall(f"{ATOM}entry"):
        link = entrada.findtext(
            f"{ATOM}id",
            default="",
        ).replace("http://", "https://", 1)

        artigo = criar_artigo(
            titulo=entrada.findtext(f"{ATOM}title"),
            link=link,
            fonte="arXiv",
            idioma="en",
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

        if link not in links:
            resultado.append(artigo)
            links.add(link)

    return resultado


def coletar_fontes(termo_arxiv):
    tarefas = {
        "arXiv": lambda: buscar_artigos(termo_arxiv)
    }

    for nome, config in FONTES_RSS.items():
        tarefas[nome] = (
            lambda nome=nome, config=config:
            buscar_rss(nome, config)
        )

    resultados = {}
    indisponiveis = []

    with ThreadPoolExecutor(
        max_workers=len(tarefas)
    ) as executor:
        futuros = {
            executor.submit(funcao): nome
            for nome, funcao in tarefas.items()
        }

        for futuro in as_completed(futuros):
            nome = futuros[futuro]

            try:
                resultados[nome] = futuro.result()

            except (
                urllib.error.URLError,
                TimeoutError,
                OSError,
                ET.ParseError,
                ValueError,
            ) as erro:
                logger.warning(
                    "Fonte indisponível %s: %s",
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


def pontuar_artigo(artigo, termos):
    titulo = normalizar(artigo["titulo"])
    resumo = normalizar(artigo.get("resumo", ""))
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


def selecionar_artigos(artigos, limite=5):
    grupos = {
        "pt": [],
        "en": [],
    }

    for artigo in artigos:
        idioma = artigo.get("idioma", "en")
        grupos.setdefault(idioma, []).append(artigo)

    selecionados = []
    links = set()
    fontes = set()

    def adicionar(artigo):
        if len(selecionados) >= limite:
            return False

        if artigo["link"] in links:
            return False

        selecionados.append(artigo)
        links.add(artigo["link"])
        fontes.add(artigo["fonte"])

        return True

    def preencher(grupo, quantidade):
        for artigo in grupo:
            if quantidade <= 0:
                break

            if (
                artigo["fonte"] not in fontes
                and adicionar(artigo)
            ):
                quantidade -= 1

        for artigo in grupo:
            if quantidade <= 0:
                break

            if adicionar(artigo):
                quantidade -= 1

    preencher(
        grupos["pt"],
        min(2, limite),
    )

    preencher(
        grupos["en"],
        min(3, limite - len(selecionados)),
    )

    restantes = sorted(
        artigos,
        key=lambda artigo: (
            artigo.get("_pontuacao", 0),
            artigo.get("data_publicacao") or "",
        ),
        reverse=True,
    )

    preencher(
        restantes,
        limite - len(selecionados),
    )

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

    artigos = sorted(
        resultado["artigos"],
        key=lambda artigo: (
            artigo.get("data_publicacao") or ""
        ),
        reverse=True,
    )

    selecionados = selecionar_artigos(
        artigos,
        LIMITE_RECOMENDACOES,
    )

    return {
        **resultado,
        "artigos": selecionados,
        "total": len(selecionados),
    }


def buscar_conteudos(pergunta):
    resultado = coletar_fontes(pergunta)
    termos = extrair_termos(pergunta)
    relevantes = []

    for artigo in resultado["artigos"]:
        pontos = pontuar_artigo(
            artigo,
            termos,
        )

        if artigo["fonte"] == "arXiv":
            pontos = max(pontos, 1)

        if pontos > 0:
            relevantes.append({
                **artigo,
                "_pontuacao": pontos,
            })

    relevantes.sort(
        key=lambda artigo: (
            artigo["_pontuacao"],
            artigo.get("data_publicacao") or "",
        ),
        reverse=True,
    )

    selecionados = selecionar_artigos(
        relevantes,
        LIMITE_RECOMENDACOES,
    )

    return {
        **resultado,
        "artigos": selecionados,
    }
