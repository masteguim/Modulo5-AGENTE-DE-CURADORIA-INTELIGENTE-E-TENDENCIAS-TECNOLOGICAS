import json
import re
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException

GITHUB_API = "https://api.github.com"
MAX_ARQUIVOS = 10000

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


def normalizar_repositorio(repositorio):
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


def requisitar_github(caminho):
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
            requisicao, timeout=12
        ) as resposta:
            conteudo = resposta.read(2_000_001)

            if len(conteudo) > 2_000_000:
                raise HTTPException(
                    status_code=502,
                    detail="Resposta do GitHub muito grande.",
                )

            return json.loads(conteudo)

    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            raise HTTPException(
                status_code=404,
                detail="Repositório não encontrado ou não público.",
            ) from erro

        if erro.code in (403, 429):
            raise HTTPException(
                status_code=503,
                detail="Limite da API pública do GitHub atingido.",
            ) from erro

        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar GitHub.",
        ) from erro

    except (urllib.error.URLError, TimeoutError) as erro:
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
    except HTTPException:
        return ""

    if not isinstance(dados, dict):
        return ""

    if dados.get("size", 0) > 100_000:
        return ""

    import base64

    if dados.get("encoding") == "base64":
        try:
            return base64.b64decode(
                dados.get("content", "")
            ).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            return ""

    return ""


def identificar_dependencias(conteudo, tecnologias):
    for dependencia, tecnologia in DEPENDENCIAS.items():
        padrao = (
            r"(?<![a-zA-Z0-9_-])"
            + re.escape(dependencia)
            + r"(?![a-zA-Z0-9_-])"
        )

        if re.search(padrao, conteudo, re.IGNORECASE):
            tecnologias.add(tecnologia)


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

    if arvore.get("truncated"):
        raise HTTPException(
            status_code=422,
            detail="Repositório muito grande para análise completa.",
        )

    arquivos = [
        item["path"]
        for item in arvore.get("tree", [])
        if item.get("type") == "blob"
    ]

    if len(arquivos) > MAX_ARQUIVOS:
        raise HTTPException(
            status_code=422,
            detail="Quantidade de arquivos acima do limite.",
        )

    tecnologias = set()
    arquivos_relevantes = []

    for caminho in arquivos:
        nome = caminho.rsplit("/", 1)[-1].lower()
        extensao = "." + nome.rsplit(".", 1)[-1]

        for tecnologia, regras in TECNOLOGIAS.items():
            if (
                nome in regras["arquivos"]
                or extensao in regras["extensoes"]
            ):
                tecnologias.add(tecnologia)

        if caminho.startswith(".github/workflows/"):
            tecnologias.add("GitHub Actions")

        if nome in {
            "package.json",
            "requirements.txt",
            "pyproject.toml",
            "dockerfile",
            "compose.yml",
            "compose.yaml",
            "docker-compose.yml",
        }:
            arquivos_relevantes.append(caminho)

    for caminho in arquivos_relevantes[:20]:
        nome = caminho.rsplit("/", 1)[-1].lower()

        if nome in {
            "package.json",
            "requirements.txt",
            "pyproject.toml",
        }:
            conteudo = ler_arquivo(repositorio, caminho)
            identificar_dependencias(conteudo, tecnologias)

    return {
        "repositorio": repositorio,
        "stack_detectada": sorted(tecnologias),
        "arquivos_analisados": arquivos_relevantes,
        "total_arquivos": len(arquivos),
        "branch": branch,
    }
