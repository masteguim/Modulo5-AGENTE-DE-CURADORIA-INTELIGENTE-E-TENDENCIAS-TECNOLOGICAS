import base64
import gzip
import json
import logging
import os
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from threading import Lock

from fastapi import HTTPException


logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

MAX_ARQUIVOS = 10000
MAX_RESPOSTA = 10_000_000
MAX_ARQUIVO_CONTEUDO = 100_000

# Limites para analisar repositórios grandes sem
# carregar toda a árvore de arquivos do GitHub.
MAX_ARVORES_PARCIAIS = 60
MAX_PROFUNDIDADE = 5

# Tamanho do repositório informado pelo GitHub em KB.
LIMITE_REPOSITORIO_COMPLETO_KB = 20_000

CACHE_TTL = 600

_cache = {}
_cache_lock = Lock()


TECNOLOGIAS = {
    "Python": {
        "arquivos": {"requirements.txt", "pyproject.toml", "pipfile"},
        "extensoes": {".py"},
    },
    "JavaScript": {
        "arquivos": {"package.json"},
        "extensoes": {".js", ".jsx"},
    },
    "TypeScript": {
        "arquivos": {"tsconfig.json"},
        "extensoes": {".ts", ".tsx"},
    },
    "Docker": {
        "arquivos": {"dockerfile", "docker-compose.yml", "compose.yml", "compose.yaml"},
        "extensoes": set(),
    },
    "GitHub Actions": {
        "arquivos": set(),
        "extensoes": set(),
    },
}


DEPENDENCIAS = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "uvicorn": "Uvicorn",
    "pytest": "Pytest",
    "pydantic": "Pydantic",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "qiskit": "Qiskit",
    "react": "React",
    "react-dom": "React",
    "vite": "Vite",
    "next": "Next.js",
    "express": "Express",
    "vue": "Vue",
    "angular": "Angular",
    "typescript": "TypeScript",
    "tailwindcss": "Tailwind CSS",
}


ARQUIVOS_RELEVANTES = {
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "dockerfile",
    "docker-compose.yml",
    "compose.yml",
    "compose.yaml",
}


ARQUIVOS_DEPENDENCIAS = {
    "package.json",
    "requirements.txt",
    "pyproject.toml",
}


DIRETORIOS_IGNORADOS = {
    ".git",
    ".next",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    "coverage",
    ".cache",
}


DIRETORIOS_PRIORITARIOS = {
    ".github",
    "src",
    "app",
    "apps",
    "packages",
    "frontend",
    "backend",
    "server",
    "client",
    "api",
    "web",
    "lib",
    "libs",
    "tests",
    "test",
    "scripts",
    "components",
    "examples",
}


def obter_cache(chave):
    with _cache_lock:
        entrada = _cache.get(chave)

        if entrada is None:
            return None

        expiracao, valor = entrada

        if time.monotonic() >= expiracao:
            del _cache[chave]
            return None

        return valor


def salvar_cache(chave, valor):
    with _cache_lock:
        _cache[chave] = (
            time.monotonic() + CACHE_TTL,
            valor,
        )


def normalizar_repositorio(repositorio):
    if not isinstance(repositorio, str):
        raise HTTPException(
            status_code=400,
            detail="Informe um repositório válido.",
        )

    valor = repositorio.strip()
    valor = re.sub(
        r"^https?://github\.com/",
        "",
        valor,
        flags=re.IGNORECASE,
    )
    valor = valor.rstrip("/")

    if not re.fullmatch(
        r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+",
        valor,
    ):
        raise HTTPException(
            status_code=400,
            detail="Informe usuario/repositorio válido.",
        )

    return valor


def _decodificar_resposta(conteudo, resposta, caminho):
    encoding = (
        resposta.headers.get("Content-Encoding", "")
        .strip()
        .lower()
    )

    if encoding == "gzip" or conteudo.startswith(b"\x1f\x8b"):
        try:
            conteudo = gzip.decompress(conteudo)
        except (OSError, EOFError) as erro:
            logger.warning(
                "Falha ao descompactar resposta do GitHub: %s",
                caminho,
            )

            raise HTTPException(
                status_code=502,
                detail="Resposta comprimida inválida do GitHub.",
            ) from erro

        if len(conteudo) > MAX_RESPOSTA:
            raise HTTPException(
                status_code=502,
                detail="Resposta do GitHub muito grande.",
            )

    if not conteudo.strip():
        raise HTTPException(
            status_code=502,
            detail="O GitHub retornou uma resposta vazia.",
        )

    try:
        return json.loads(conteudo)

    except (json.JSONDecodeError, UnicodeDecodeError) as erro:
        logger.warning(
            "JSON inválido do GitHub em %s. "
            "Content-Type: %s. Tamanho: %d bytes.",
            caminho,
            resposta.headers.get("Content-Type"),
            len(conteudo),
        )

        raise HTTPException(
            status_code=502,
            detail="O GitHub retornou uma resposta inválida.",
        ) from erro


def requisitar_github(caminho):
    if not isinstance(caminho, str) or not caminho.startswith("/"):
        raise ValueError("Caminho inválido da API GitHub.")

    # Impede consultas a domínios externos através
    # de um caminho de API fornecido indevidamente.
    if caminho.startswith("//"):
        raise ValueError("Caminho inválido da API GitHub.")

    cache = obter_cache(caminho)

    if cache is not None:
        return cache

    headers = {
        "Accept": "application/vnd.github+json",
        "Accept-Encoding": "identity",
        "User-Agent": "Agente-Curadoria-Mackenzie",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    token = os.getenv("GITHUB_TOKEN", "").strip()

    if token:
        headers["Authorization"] = f"Bearer {token}"

    requisicao = urllib.request.Request(
        f"{GITHUB_API}{caminho}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Agente-Curadoria-Mackenzie",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    try:
        with urllib.request.urlopen(
            requisicao,
            timeout=20,
            requisicao, timeout=12
        ) as resposta:
            conteudo = resposta.read(MAX_RESPOSTA + 1)

            if len(conteudo) > MAX_RESPOSTA:
                logger.warning(
                    "Resposta do GitHub excedeu %d bytes: %s",
                    MAX_RESPOSTA,
                    caminho,
                )

                raise HTTPException(
                    status_code=502,
                    detail="Resposta do GitHub muito grande.",
                )

            dados = _decodificar_resposta(
                conteudo,
                resposta,
                caminho,
            )

            salvar_cache(caminho, dados)

            return dados
            return json.loads(conteudo)

    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Repositório ou recurso não encontrado "
                    "ou não público."
                ),
            ) from erro

        if erro.code == 401:
            raise HTTPException(
                status_code=502,
                detail="Token do GitHub inválido ou expirado.",
                detail="Repositório não encontrado ou não público.",
            ) from erro

        if erro.code in (403, 429):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Limite da API do GitHub atingido "
                    "ou acesso temporariamente restrito."
                ),
                detail="Limite da API pública do GitHub atingido.",
            ) from erro

        logger.warning(
            "Erro HTTP %s ao consultar %s",
            erro.code,
            caminho,
        )

        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar GitHub.",
        ) from erro

    except (urllib.error.URLError, TimeoutError) as erro:
        logger.warning(
            "Falha de conexão ao consultar %s: %s",
            caminho,
            erro,
        )

        raise HTTPException(
            status_code=503,
            detail="Não foi possível acessar o GitHub.",
        ) from erro


def ler_arquivo(repositorio, caminho):
    caminho_codificado = urllib.parse.quote(
        caminho, safe="/"
    )

    try:
        dados = requisitar_github(
            f"/repos/{repositorio}/contents/{caminho_codificado}"
        )

    except HTTPException as erro:
        if erro.status_code == 404:
            return ""

        raise
    except HTTPException:
        return ""

    if not isinstance(dados, dict):
        return ""

    if dados.get("type") not in (None, "file"):
        return ""

    tamanho = dados.get("size", 0)

    if not isinstance(tamanho, int):
        return ""

    if tamanho > MAX_ARQUIVO_CONTEUDO:
        return ""

    import base64

    if dados.get("encoding") == "base64":
        try:
            conteudo = base64.b64decode(
                dados.get("content", ""),
                validate=False,
            )

            return conteudo.decode(
                "utf-8",
                errors="replace",
            )

        except (ValueError, TypeError, UnicodeError):
            logger.warning(
                "Não foi possível decodificar o arquivo %s",
                caminho,
            )

            return base64.b64decode(
                dados.get("content", "")
            ).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            return ""

    return ""


def identificar_dependencias(conteudo, tecnologias):
    if not conteudo:
        return

    for dependencia, tecnologia in DEPENDENCIAS.items():
        padrao = (
            r"(?<![a-zA-Z0-9_-])"
            + re.escape(dependencia)
            + r"(?![a-zA-Z0-9_-])"
        )

        if re.search(padrao, conteudo, re.IGNORECASE):
            tecnologias.add(tecnologia)


def _listar_arvore_completa(repositorio, branch):
def detectar_stack(repositorio):
    repositorio = normalizar_repositorio(repositorio)
    metadados = requisitar_github(
        f"/repos/{repositorio}"
    )

    if metadados.get("private"):
        raise HTTPException(
            status_code=400,
            detail="Somente repositórios públicos são suportados.",
        )

    branch = metadados.get("default_branch", "main")
    branch_codificada = urllib.parse.quote(
        branch, safe=""
    )

    arvore = requisitar_github(
        f"/repos/{repositorio}/git/trees/"
        f"{branch_codificada}?recursive=1"
    )

    if not isinstance(arvore, dict):
        raise HTTPException(
            status_code=502,
            detail="Estrutura de arquivos inválida do GitHub.",
            status_code=422,
            detail="Repositório muito grande para análise completa.",
        )

    if arvore.get("truncated"):
        return None

    arquivos = [
        item["path"]
        for item in arvore.get("tree", [])
        if (
            isinstance(item, dict)
            and item.get("type") == "blob"
            and isinstance(item.get("path"), str)
        )
    ]

    if len(arquivos) > MAX_ARQUIVOS:
        return None

    return arquivos


def _prioridade_diretorio(nome):
    nome = nome.lower()

    if nome in DIRETORIOS_PRIORITARIOS:
        return 0

    return 1


def _listar_arvore_parcial(repositorio, branch):
    """
    Percorre um número limitado de diretórios para
    detectar tecnologias em repositórios grandes.

    Essa análise não representa uma varredura completa.
    """

    branch_codificada = urllib.parse.quote(
        branch,
        safe="",
    )

    fila = deque([
        (branch_codificada, "", 0)
    ])

    arquivos = []
    visitados = set()
    arvores_consultadas = 0

    while fila and arvores_consultadas < MAX_ARVORES_PARCIAIS:
        referencia, prefixo, profundidade = fila.popleft()

        if referencia in visitados:
            continue

        visitados.add(referencia)

        arvore = requisitar_github(
            f"/repos/{repositorio}/git/trees/{referencia}"
        )

        arvores_consultadas += 1

        if not isinstance(arvore, dict):
            continue

        itens = arvore.get("tree", [])

        if not isinstance(itens, list):
            continue

        diretorios = []

        for item in itens:
            if not isinstance(item, dict):
                continue

            nome = item.get("path")
            tipo = item.get("type")
            sha = item.get("sha")

            if not isinstance(nome, str):
                continue

            caminho = (
                f"{prefixo}/{nome}"
                if prefixo
                else nome
            )

            if tipo == "blob":
                arquivos.append(caminho)

                if len(arquivos) >= MAX_ARQUIVOS:
                    return arquivos

            elif (
                tipo == "tree"
                and isinstance(sha, str)
                and profundidade < MAX_PROFUNDIDADE
                and nome.lower() not in DIRETORIOS_IGNORADOS
            ):
                diretorios.append(
                    (
                        _prioridade_diretorio(nome),
                        nome,
                        sha,
                        caminho,
                    )
                )

        diretorios.sort(
            key=lambda item: (item[0], item[1].lower())
        )

        for _, _, sha, caminho in diretorios:
            fila.append(
                (sha, caminho, profundidade + 1)
            )

    logger.info(
        "Análise parcial de %s: %d árvores e %d arquivos.",
        repositorio,
        arvores_consultadas,
        len(arquivos),
    )

    return arquivos


def _obter_arquivos_repositorio(repositorio, branch, tamanho_kb):
    """
    Tenta analisar a árvore completa de repositórios
    menores. Em repositórios grandes ou com respostas
    excessivas, utiliza uma análise parcial.
    """

    analise_parcial = False
    arquivos = None

    if tamanho_kb <= LIMITE_REPOSITORIO_COMPLETO_KB:
        try:
            arquivos = _listar_arvore_completa(
                repositorio,
                branch,
            )

        except HTTPException as erro:
            # Somente erros relacionados a tamanho ou
            # formato da árvore provocam análise parcial.
            # Problemas de autenticação e indisponibilidade
            # continuam sendo propagados normalmente.
            if erro.status_code != 502:
                raise

            logger.warning(
                "Não foi possível carregar a árvore "
                "completa de %s: %s",
                repositorio,
                erro.detail,
            )

    if arquivos is None:
        analise_parcial = True

        arquivos = _listar_arvore_parcial(
            repositorio,
            branch,
        raise HTTPException(
            status_code=422,
            detail="Quantidade de arquivos acima do limite.",
        )

    return arquivos, analise_parcial


def _analisar_caminhos(repositorio, arquivos):
    tecnologias = set()
    arquivos_relevantes = []

    for caminho in arquivos:
        nome = caminho.rsplit("/", 1)[-1].lower()

        extensao = (
            "." + nome.rsplit(".", 1)[-1]
            if "." in nome
            else ""
        )
        extensao = "." + nome.rsplit(".", 1)[-1]

        for tecnologia, regras in TECNOLOGIAS.items():
            if (
                nome in regras["arquivos"]
                or extensao in regras["extensoes"]
            ):
                tecnologias.add(tecnologia)

        if caminho.startswith(".github/workflows/"):
            tecnologias.add("GitHub Actions")

        if nome in ARQUIVOS_RELEVANTES:
            arquivos_relevantes.append(caminho)

    # Prioriza arquivos de configuração próximos
    # à raiz antes de consultar arquivos internos.
    arquivos_relevantes = sorted(
        set(arquivos_relevantes),
        key=lambda caminho: (
            caminho.count("/"),
            caminho.lower(),
        ),
    )

    for caminho in arquivos_relevantes[:20]:
        nome = caminho.rsplit("/", 1)[-1].lower()

        if nome not in ARQUIVOS_DEPENDENCIAS:
            continue

        try:
            conteudo = ler_arquivo(
                repositorio,
                caminho,
            )

            identificar_dependencias(
                conteudo,
                tecnologias,
            )
        if nome in {
            "package.json",
            "requirements.txt",
            "pyproject.toml",
        }:
            conteudo = ler_arquivo(repositorio, caminho)
            identificar_dependencias(conteudo, tecnologias)

        except HTTPException as erro:
            # Se o GitHub ficar temporariamente
            # indisponível, preservamos as tecnologias
            # já detectadas pelos nomes dos arquivos.
            if erro.status_code in (502, 503):
                logger.warning(
                    "Não foi possível analisar %s: %s",
                    caminho,
                    erro.detail,
                )
                continue

            raise

    return tecnologias, arquivos_relevantes


def detectar_stack(repositorio):
    repositorio = normalizar_repositorio(
        repositorio
    )

    metadados = requisitar_github(
        f"/repos/{repositorio}"
    )

    if not isinstance(metadados, dict):
        raise HTTPException(
            status_code=502,
            detail="Metadados inválidos do repositório.",
        )

    if metadados.get("private"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Somente repositórios públicos "
                "são suportados."
            ),
        )

    branch = metadados.get(
        "default_branch"
    ) or "main"

    tamanho_kb = metadados.get("size", 0)

    if not isinstance(tamanho_kb, int):
        tamanho_kb = LIMITE_REPOSITORIO_COMPLETO_KB + 1

    arquivos, analise_parcial = _obter_arquivos_repositorio(
        repositorio,
        branch,
        tamanho_kb,
    )

    tecnologias, arquivos_relevantes = _analisar_caminhos(
        repositorio,
        arquivos,
    )

    return {
        "repositorio": repositorio,
        "stack_detectada": sorted(tecnologias),
        "arquivos_analisados": arquivos_relevantes,
        "total_arquivos": len(arquivos),
        "branch": branch,
        "analise_parcial": analise_parcial,
    }
