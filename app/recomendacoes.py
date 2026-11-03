
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.curadoria import (
    coletar_fontes,
    normalizar,
    pontuar_artigo,
    remover_duplicados,
)

LIMITE_GERAL = 10
LIMITE_CATEGORIA = 5

CATEGORIAS = {
    "inteligencia-artificial": {
        "nome": "Inteligência Artificial",
        "busca": "artificial intelligence",
        "termos": [
            "artificial intelligence",
            "inteligencia artificial",
            "machine learning",
            "aprendizado de maquina",
            "deep learning",
            "neural network",
            "llm",
            "generative ai",
            "agents",
            "agentes de ia",
        ],
    },
    "desenvolvimento": {
        "nome": "Desenvolvimento de Software",
        "busca": "software engineering",
        "termos": [
            "software",
            "programming",
            "programacao",
            "developer",
            "desenvolvedor",
            "javascript",
            "typescript",
            "python",
            "react",
            "fastapi",
            "framework",
            "github copilot",
        ],
    },
    "seguranca": {
        "nome": "Segurança",
        "busca": "computer security",
        "termos": [
            "security",
            "seguranca",
            "cybersecurity",
            "ciberseguranca",
            "vulnerability",
            "vulnerabilidade",
            "cve",
            "malware",
            "ransomware",
            "authentication",
            "autenticacao",
            "exploit",
        ],
    },
    "devops": {
        "nome": "DevOps e Infraestrutura",
        "busca": "cloud computing",
        "termos": [
            "devops",
            "docker",
            "kubernetes",
            "cloud",
            "nuvem",
            "azure",
            "aws",
            "deployment",
            "deploy",
            "ci/cd",
            "github actions",
            "infrastructure",
            "infraestrutura",
            "container",
        ],
    },
    "computacao-quantica": {
        "nome": "Computação Quântica",
        "busca": "quantum computing",
        "termos": [
            "quantum",
            "quantica",
            "quantico",
            "qubit",
            "qiskit",
            "quantum computing",
            "computacao quantica",
            "quantum processor",
            "quantum algorithm",
        ],
    },
}

TECNOLOGIAS = {
    "react": "React",
    "vite": "Vite",
    "next": "Next.js",
    "vue": "Vue",
    "angular": "Angular",
    "typescript": "TypeScript",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "pytest": "pytest",
    "pydantic": "Pydantic",
    "numpy": "NumPy",
    "qiskit": "Qiskit",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "docker": "Docker",
    "postgresql": "PostgreSQL",
    "redis": "Redis",
    "github actions": "GitHub Actions",
}

ARQUIVOS_STACK = [
    "package.json",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "Dockerfile",
    ".github/workflows/main.yml",
    ".github/workflows/main_agente-tendencias-tecnologicas.yml",
]

PADRAO_REPOSITORIO = re.compile(
    r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$"
)


def validar_repositorio(repositorio):
    if not PADRAO_REPOSITORIO.fullmatch(repositorio):
        raise ValueError(
            "Use o formato usuario/repositorio."
        )

    partes = repositorio.split("/")

    if any(parte in {".", ".."} for parte in partes):
        raise ValueError("Repositório inválido.")

    return repositorio


def requisitar_github(url):
    requisicao = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AgenteCuradoria/2.4",
            "Accept": "application/vnd.github+json",
        },
    )

    with urllib.request.urlopen(
        requisicao,
        timeout=10,
    ) as resposta:
        return resposta.read(1_000_001).decode("utf-8")


def analisar_repositorio(repositorio):
    validar_repositorio(repositorio)

    url_api = (
        "https://api.github.com/repos/"
        f"{repositorio}"
    )

    metadados = json.loads(
        requisitar_github(url_api)
    )

    if metadados.get("private"):
        raise ValueError(
            "Repositórios privados exigem autorização."
        )

    branch = metadados.get(
        "default_branch",
        "main",
    )

    base = (
        "https://raw.githubusercontent.com/"
        f"{repositorio}/"
        f"{urllib.parse.quote(branch, safe='')}/"
    )

    conteudos = {}
    arquivos_encontrados = []

    def buscar_arquivo(caminho):
        url = base + caminho

        try:
            return caminho, requisitar_github(url)
        except urllib.error.HTTPError as erro:
            if erro.code == 404:
                return caminho, None
            raise

    with ThreadPoolExecutor(
        max_workers=5
    ) as executor:
        futuros = [
            executor.submit(buscar_arquivo, caminho)
            for caminho in ARQUIVOS_STACK
        ]

        for futuro in as_completed(futuros):
            caminho, conteudo = futuro.result()

            if conteudo is not None:
                conteudos[caminho] = conteudo
                arquivos_encontrados.append(caminho)

    stack = set()

    if "package.json" in conteudos:
        pacote = json.loads(
            conteudos["package.json"]
        )

        dependencias = {
            **pacote.get("dependencies", {}),
            **pacote.get("devDependencies", {}),
        }

        for nome in dependencias:
            chave = nome.casefold()

            if chave in TECNOLOGIAS:
                stack.add(TECNOLOGIAS[chave])

        if "react" in dependencias:
            stack.add("JavaScript")

    for arquivo in (
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
    ):
        if arquivo not in conteudos:
            continue

        texto = conteudos[arquivo].casefold()

        for chave, tecnologia in TECNOLOGIAS.items():
            padrao = (
                r"(?<![a-z0-9])"
                + re.escape(chave)
                + r"(?![a-z0-9])"
            )

            if re.search(padrao, texto):
                stack.add(tecnologia)

        stack.add("Python")

    if "Dockerfile" in conteudos:
        stack.add("Docker")

    if any(
        caminho.startswith(".github/workflows/")
        for caminho in conteudos
    ):
        stack.add("GitHub Actions")

    return {
        "repositorio": repositorio,
        "stack_detectada": sorted(stack),
        "arquivos_analisados": sorted(
            arquivos_encontrados
        ),
    }


def corresponde_termo(texto, termo):
    padrao = (
        r"(?<!\w)"
        + re.escape(normalizar(termo))
        + r"(?!\w)"
    )
    return re.search(padrao, texto) is not None


def pontuar_recomendacao(
    artigo,
    categoria=None,
    stack=None,
):
    titulo = normalizar(artigo["titulo"])
    resumo = normalizar(
        artigo.get("resumo", "")
    )

    pontos = 0

    if categoria:
        termos = CATEGORIAS[categoria]["termos"]

        pontos = pontuar_artigo(
            artigo,
            termos,
        )

        if pontos == 0:
            return 0

    for tecnologia in stack or []:
        if corresponde_termo(titulo, tecnologia):
            pontos += 12

        elif corresponde_termo(
            resumo,
            tecnologia,
        ):
            pontos += 4

    return pontos


def selecionar_recomendacoes(
    artigos,
    limite,
    categoria=None,
    stack=None,
):
    candidatos = []

    for artigo in remover_duplicados(artigos):
        pontos = pontuar_recomendacao(
            artigo,
            categoria,
            stack,
        )

        if categoria and pontos <= 0:
            continue

        candidatos.append({
            **artigo,
            "_pontos": pontos,
        })

    candidatos.sort(
        key=lambda artigo: (
            artigo["_pontos"],
            artigo.get("data_publicacao") or "",
        ),
        reverse=True,
    )

    portugueses = [
        artigo for artigo in candidatos
        if artigo.get("idioma") == "pt"
    ]

    ingleses = [
        artigo for artigo in candidatos
        if artigo.get("idioma") == "en"
    ]

    selecionados = []
    links = set()

    def adicionar(artigo):
        if (
            len(selecionados) >= limite
            or artigo["link"] in links
        ):
            return False

        links.add(artigo["link"])
        selecionados.append(artigo)
        return True

    def preencher(grupo, quantidade):
        adicionados = 0

        for artigo in grupo:
            if adicionados >= quantidade:
                break

            if adicionar(artigo):
                adicionados += 1

    preencher(portugueses, round(limite * 0.4))
    preencher(ingleses, limite - len(selecionados))
    preencher(candidatos, limite - len(selecionados))

    return [
        {
            chave: valor
            for chave, valor in artigo.items()
            if not chave.startswith("_")
        }
        for artigo in selecionados
    ]


def obter_recomendacoes(
    categoria=None,
    repositorio=None,
):
    if categoria and categoria not in CATEGORIAS:
        raise ValueError("Categoria inválida.")

    contexto = {
        "repositorio": None,
        "stack_detectada": [],
        "arquivos_analisados": [],
    }

    if repositorio:
        contexto = analisar_repositorio(
            repositorio
        )

    limite = (
        LIMITE_CATEGORIA
        if categoria
        else LIMITE_GERAL
    )

    termo_busca = (
        CATEGORIAS[categoria]["busca"]
        if categoria
        else (
            " ".join(contexto["stack_detectada"][:3])
            or "machine learning"
        )
    )

    resultado = coletar_fontes(termo_busca)

    artigos = selecionar_recomendacoes(
        artigos=resultado["artigos"],
        limite=limite,
        categoria=categoria,
        stack=contexto["stack_detectada"],
    )

    return {
        "artigos": artigos,
        "total": len(artigos),
        "categoria": categoria or "geral",
        "repositorio": contexto["repositorio"],
        "stack_detectada": contexto["stack_detectada"],
        "fontes_consultadas": resultado[
            "fontes_consultadas"
        ],
        "fontes_indisponiveis": resultado[
            "fontes_indisponiveis"
        ],
    }
