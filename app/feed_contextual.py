
"""Recomendações contextuais baseadas no repositório GitHub."""

import logging
import re
import urllib.error
import xml.etree.ElementTree as ET

from app.curadoria import buscar_artigos, normalizar
from app.github_stack import ler_arquivo

logger = logging.getLogger(__name__)

PERFIS = {
    "quantico": {
        "termos": [
            "quantum computing",
            "quantum computer",
            "quantum processor",
            "quantum algorithm",
            "quantum circuit",
            "quantum simulation",
            "quantum technology",
            "qubit",
            "qiskit",
            "computacao quantica",
            "computador quantico",
        ],
        "busca": "quantum computing",
    },
    "aleatoriedade_quantica": {
        "termos": [
            "quantum random",
            "quantum randomness",
            "quantum entropy",
            "random number generation",
            "random number generator",
            "quantum measurement",
            "true random",
            "qrng",
            "gerador de numeros aleatorios",
            "medicao quantica",
        ],
        "busca": "quantum random number generator",
    },
    "inteligencia_artificial": {
        "termos": [
            "machine learning",
            "deep learning",
            "artificial intelligence",
            "neural network",
            "large language model",
            "pytorch",
            "tensorflow",
            "aprendizado de maquina",
        ],
        "busca": "machine learning",
    },
    "desenvolvimento_web": {
        "termos": [
            "react",
            "reactjs",
            "next.js",
            "frontend",
            "web application",
            "javascript framework",
            "typescript",
            "fastapi",
            "django",
            "flask",
        ],
        "busca": "web software engineering",
    },
    "devops": {
        "termos": [
            "docker",
            "kubernetes",
            "containerization",
            "continuous integration",
            "continuous deployment",
            "devops",
            "cloud infrastructure",
            "github actions",
            "ci/cd",
        ],
        "busca": "devops cloud computing",
    },
    "seguranca": {
        "termos": [
            "cybersecurity",
            "software vulnerability",
            "security vulnerability",
            "authentication security",
            "code security",
            "malware",
            "ransomware",
            "cryptography",
        ],
        "busca": "computer security",
    },
    "python_cientifico": {
        "termos": [
            "scientific computing",
            "numerical simulation",
            "numerical computing",
            "numerical analysis",
            "scientific python",
            "numpy",
            "pandas",
            "scipy",
            "computacao cientifica",
        ],
        "busca": "scientific computing python",
    },
}

CATEGORIA_PERFIS = {
    "inteligencia-artificial": {"inteligencia_artificial"},
    "desenvolvimento": {
        "desenvolvimento_web",
        "python_cientifico",
    },
    "seguranca": {"seguranca"},
    "devops": {"devops"},
    "computacao-quantica": {
        "quantico",
        "aleatoriedade_quantica",
    },
}

STACK_PERFIS = {
    "qiskit": {"quantico"},
    "pytorch": {"inteligencia_artificial"},
    "tensorflow": {"inteligencia_artificial"},
    "scikit-learn": {"inteligencia_artificial"},
    "react": {"desenvolvimento_web"},
    "next.js": {"desenvolvimento_web"},
    "fastapi": {"desenvolvimento_web"},
    "django": {"desenvolvimento_web"},
    "flask": {"desenvolvimento_web"},
    "docker": {"devops"},
    "kubernetes": {"devops"},
    "github actions": {"devops"},
    "numpy": {"python_cientifico"},
    "pandas": {"python_cientifico"},
    "scipy": {"python_cientifico"},
}


def contem_termo(texto, termo):
    termo = normalizar(termo)

    if not termo:
        return False

    padrao = (
        r"(?<!\w)"
        + re.escape(termo)
        + r"(?!\w)"
    )

    return re.search(padrao, texto) is not None


def obter_descricao_projeto(repositorio):
    """Consulta o README público, sem impedir o feed se falhar."""

    for nome in ("README.md", "readme.md", "README.rst"):
        try:
            conteudo = ler_arquivo(repositorio, nome)
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
        ):
            logger.warning(
                "README indisponível para %s",
                repositorio,
            )
            return ""

        if conteudo:
            return normalizar(conteudo[:15000])

    return ""


def identificar_perfis(contexto, descricao=""):
    """Identifica assuntos com base na stack e no projeto."""

    stack = {
        normalizar(tecnologia)
        for tecnologia in contexto.get("stack", [])
    }

    perfis = set()

    for tecnologia in stack:
        perfis.update(
            STACK_PERFIS.get(tecnologia, set())
        )

    repositorio = normalizar(
        contexto.get("repositorio") or ""
    )

    texto = f"{repositorio} {descricao}"

    termos_quanticos = (
        "quantum",
        "quantica",
        "quantico",
        "qubit",
        "qiskit",
    )

    termos_aleatoriedade = (
        "random",
        "aleatori",
        "pseudorrandom",
        "pseudoaleatori",
        "qrng",
        "entropia",
    )

    if any(termo in texto for termo in termos_quanticos):
        perfis.add("quantico")

    if (
        "quantico" in perfis
        and any(
            termo in texto
            for termo in termos_aleatoriedade
        )
    ):
        perfis.add("aleatoriedade_quantica")

    if any(
        termo in texto
        for termo in (
            "machine learning",
            "deep learning",
            "inteligencia artificial",
        )
    ):
        perfis.add("inteligencia_artificial")

    return perfis


def pontuar_artigo_contextual(artigo, perfis):
    """Prioriza assunto relacionado em vez de idioma ou fonte."""

    titulo = normalizar(artigo.get("titulo") or "")
    resumo = normalizar(artigo.get("resumo") or "")

    pontuacao = 0

    for perfil in perfis:
        for termo in PERFIS[perfil]["termos"]:
            if contem_termo(titulo, termo):
                pontuacao += 12
            elif contem_termo(resumo, termo):
                pontuacao += 5

    return pontuacao


def selecionar_contextuais(
    artigos,
    perfis,
    limite,
    pontuacao_minima=10,
):
    """Remove irrelevantes e ordena os artigos mais relacionados."""

    candidatos = {}
    for artigo in artigos:
        link = artigo.get("link") or ""
        titulo = artigo.get("titulo") or ""

        if not link.startswith("https://") or not titulo:
            continue

        pontos = pontuar_artigo_contextual(
            artigo,
            perfis,
        )

        if pontos < pontuacao_minima:
            continue

        candidato = {
            **artigo,
            "_pontuacao_contextual": pontos,
        }

        anterior = candidatos.get(link)

        if (
            anterior is None
            or pontos > anterior["_pontuacao_contextual"]
        ):
            candidatos[link] = candidato

    ordenados = sorted(
        candidatos.values(),
        key=lambda artigo: (
            artigo["_pontuacao_contextual"],
            artigo.get("data_publicacao")
            or artigo.get("coletado_em")
            or "",
        ),
        reverse=True,
    )

    resultado = []

    for artigo in ordenados[:limite]:
        resultado.append({
            "titulo": artigo["titulo"],
            "link": artigo["link"],
            "fonte": artigo.get("fonte", "Desconhecida"),
            "idioma": artigo.get("idioma", "en"),
            "data_publicacao": artigo.get(
                "data_publicacao"
            ),
            "resumo": artigo.get("resumo", ""),
        })

    return resultado


def buscar_artigos_direcionados(perfis):
    """Busca artigos reais no arXiv para os temas identificados."""

    artigos = []
    indisponiveis = []

    # Limitamos a duas buscas por requisição.
    prioridades = [
        "aleatoriedade_quantica",
        "quantico",
        "inteligencia_artificial",
        "devops",
        "seguranca",
        "desenvolvimento_web",
        "python_cientifico",
    ]

    selecionados = [
        perfil
        for perfil in prioridades
        if perfil in perfis
    ][:2]

    for perfil in selecionados:
        termo = PERFIS[perfil]["busca"]

        try:
            encontrados = buscar_artigos(termo)
            artigos.extend(encontrados)

        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            ET.ParseError,
        ):
            logger.warning(
                "Busca arXiv indisponível: %s",
                termo,
            )
            indisponiveis.append(
                f"arXiv: {termo}"
            )

    return artigos, indisponiveis


def gerar_feed_contextual(
    categoria,
    contexto,
    artigos_banco,
    limite,
):
    """Gera recomendações relevantes ao repositório."""

    repositorio = contexto.get("repositorio")
    descricao = (
        obter_descricao_projeto(repositorio)
        if repositorio
        else ""
    )

    perfis_projeto = identificar_perfis(
        contexto,
        descricao,
    )

    perfis = set(perfis_projeto)

    if categoria != "geral":
        perfis &= CATEGORIA_PERFIS.get(
            categoria,
            set(),
        )

    fontes = {
        artigo.get("fonte", "Desconhecida")
        for artigo in artigos_banco
    }

    artigos = selecionar_contextuais(
        artigos_banco,
        perfis,
        limite,
    )

    indisponiveis = []

    if perfis and len(artigos) < limite:
        novos, indisponiveis = buscar_artigos_direcionados(
            perfis
        )

        fontes.update(
            artigo.get("fonte", "arXiv")
            for artigo in novos
        )

        artigos = selecionar_contextuais(
            artigos_banco + novos,
            perfis,
            limite,
        )

    return {
        "artigos": artigos,
        "total": len(artigos),
        "categoria": categoria,
        "repositorio": repositorio,
        "stack_detectada": contexto.get("stack", []),
        "tecnologias_alteradas": contexto.get(
            "tecnologias_alteradas",
            [],
        ),
        "termos_recomendacao": contexto.get(
            "termos_alteracoes",
            [],
        ),
        "fontes_consultadas": sorted(fontes),
        "fontes_indisponiveis": indisponiveis,
    }
