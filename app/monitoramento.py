import json
import logging
import os
import re
import sys
from collections import Counter
from urllib.parse import quote, urlparse

import httpx


logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

TECNOLOGIAS_ARQUIVOS = {
    "Python": [".py", "requirements.txt", "pyproject.toml"],
    "FastAPI": ["main.py", "schemas.py", "routers/", "api/"],
    "React": [".jsx", ".tsx", "src/components/", "src/pages/"],
    "JavaScript": [".js", ".jsx", ".mjs", ".cjs"],
    "TypeScript": [".ts", ".tsx"],
    "Docker": ["dockerfile", "docker-compose.yml", "compose.yaml"],
    "GitHub Actions": [".github/workflows/"],
    "HTML": [".html"],
    "CSS": [".css"],
    "Java": [".java", "pom.xml", "build.gradle"],
    "C": [".c", ".h"],
    "C++": [".cpp", ".hpp", ".cc"],
    "Go": [".go", "go.mod"],
    "Rust": [".rs", "cargo.toml"],
    "SQL": [".sql"],
    "Jupyter": [".ipynb"],
}

TECNOLOGIAS_CONTEUDO = {
    "FastAPI": ["fastapi", "uvicorn"],
    "Flask": ["flask"],
    "Django": ["django"],
    "React": ["react", "vite"],
    "Docker": ["docker", "container"],
    "GitHub Actions": ["workflow", "ci/cd"],
    "SQLite": ["sqlite", ".db"],
    "Pydantic": ["pydantic"],
    "Pytest": ["pytest"],
    "Qiskit": ["qiskit", "quantum"],
    "Azure": ["azure", "webapp"],
}

STATUS_ARQUIVOS = {
    "added": "adicionado",
    "modified": "modificado",
    "removed": "removido",
    "renamed": "renomeado",
    "copied": "copiado",
    "changed": "alterado",
    "unchanged": "inalterado",
}


def normalizar_repositorio(repositorio):
    repositorio = repositorio.strip()

    if repositorio.startswith(("http://", "https://")):
        url = urlparse(repositorio)

        if (
            url.hostname != "github.com"
            or url.username
            or url.password
            or url.port
        ):
            raise ValueError(
                "O repositório deve pertencer ao github.com."
            )

        repositorio = url.path.strip("/")

    repositorio = repositorio.removesuffix(".git")

    partes = repositorio.strip("/").split("/")

    if len(partes) != 2:
        raise ValueError(
            "Use o formato usuario/repositorio."
        )

    for parte in partes:
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+", parte)
            or parte in (".", "..")
        ):
            raise ValueError(
                "Nome de repositório inválido."
            )

    return "/".join(partes)


def criar_cliente():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Agente-Curadoria-Modulo5",
    }

    token = os.getenv("GITHUB_TOKEN")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return httpx.Client(
        base_url=GITHUB_API,
        headers=headers,
        timeout=20,
        follow_redirects=False,
    )


def consultar_github(cliente, caminho, parametros=None):
    resposta = cliente.get(
        caminho,
        params=parametros,
    )

    if resposta.status_code == 404:
        raise ValueError(
            "Repositório ou commit não encontrado, "
            "ou sem permissão de acesso."
        )

    if resposta.status_code in (401, 403, 429):
        raise RuntimeError(
            "Acesso ao GitHub negado ou limite "
            "de requisições atingido. "
            "Verifique o GITHUB_TOKEN."
        )

    resposta.raise_for_status()

    return resposta.json()


def identificar_tecnologias(caminho):
    caminho = caminho.lower()
    tecnologias = set()

    for tecnologia, padroes in TECNOLOGIAS_ARQUIVOS.items():
        for padrao in padroes:
            if padrao.startswith(".") and "/" not in padrao:
                corresponde = caminho.endswith(padrao)
            else:
                corresponde = (
                    padrao in caminho
                )

            if corresponde:
                tecnologias.add(tecnologia)
                break

    for tecnologia, termos in TECNOLOGIAS_CONTEUDO.items():
        if any(termo in caminho for termo in termos):
            tecnologias.add(tecnologia)

    return sorted(tecnologias)


def analisar_arquivo(arquivo):
    caminho = arquivo.get("filename", "")

    tecnologias = identificar_tecnologias(
        caminho
    )

    return {
        "arquivo": caminho,
        "status": STATUS_ARQUIVOS.get(
            arquivo.get("status"),
            arquivo.get("status", "desconhecido"),
        ),
        "adicoes": arquivo.get("additions", 0),
        "remocoes": arquivo.get("deletions", 0),
        "alteracoes": arquivo.get("changes", 0),
        "tecnologias": tecnologias,
        "link": arquivo.get("blob_url"),
    }


def analisar_commit(commit):
    informacoes = commit.get("commit") or {}
    autor = informacoes.get("author") or {}

    arquivos = [
        analisar_arquivo(arquivo)
        for arquivo in commit.get("files", [])
    ]

    tecnologias = sorted({
        tecnologia
        for arquivo in arquivos
        for tecnologia in arquivo["tecnologias"]
    })

    return {
        "sha": commit.get("sha"),
        "mensagem": informacoes.get("message", ""),
        "autor": autor.get("name", "Desconhecido"),
        "data": autor.get("date"),
        "link": commit.get("html_url"),
        "total_arquivos": len(arquivos),
        "adicoes": (commit.get("stats") or {}).get(
            "additions", 0
        ),
        "remocoes": (commit.get("stats") or {}).get(
            "deletions", 0
        ),
        "tecnologias": tecnologias,
        "arquivos": arquivos,
    }


def gerar_resumo(commits):
    arquivos_unicos = {}
    frequencias = Counter()

    total_adicoes = 0
    total_remocoes = 0

    for commit in commits:
        total_adicoes += commit["adicoes"]
        total_remocoes += commit["remocoes"]

        for arquivo in commit["arquivos"]:
            caminho = arquivo["arquivo"]
            arquivos_unicos[caminho] = arquivo

            for tecnologia in arquivo["tecnologias"]:
                frequencias[tecnologia] += 1

    return {
        "total_commits": len(commits),
        "total_arquivos_unicos": len(arquivos_unicos),
        "total_adicoes": total_adicoes,
        "total_remocoes": total_remocoes,
        "tecnologias_alteradas": [
            {
                "tecnologia": tecnologia,
                "ocorrencias": quantidade,
            }
            for tecnologia, quantidade
            in frequencias.most_common()
        ],
        "arquivos_recentes": list(
            arquivos_unicos.values()
        ),
    }


def gerar_termos_recomendacao(resumo):
    termos = set()

    for item in resumo["tecnologias_alteradas"]:
        termos.add(item["tecnologia"].lower())

    for arquivo in resumo["arquivos_recentes"]:
        caminho = arquivo["arquivo"].lower()

        if "docker" in caminho:
            termos.add("docker security")

        if "requirements" in caminho:
            termos.add("python dependencies")

        if "package.json" in caminho:
            termos.add("npm dependencies")

        if ".github/workflows/" in caminho:
            termos.add("github actions")

        if "test" in caminho:
            termos.add("software testing")

        if "api" in caminho or "main.py" in caminho:
            termos.add("api development")

        if ".jsx" in caminho or ".tsx" in caminho:
            termos.add("react development")

    return sorted(termos)


def monitorar_repositorio(repositorio, limite=5):
    repositorio = normalizar_repositorio(
        repositorio
    )

    limite = max(1, min(int(limite), 20))

    caminho_base = "/repos/" + "/".join(
        quote(parte, safe="")
        for parte in repositorio.split("/")
    )

    commits_analisados = []
    erros = []

    with criar_cliente() as cliente:
        commits_recentes = consultar_github(
            cliente,
            f"{caminho_base}/commits",
            {"per_page": limite},
        )

        if not isinstance(commits_recentes, list):
            raise RuntimeError(
                "Resposta inesperada da API do GitHub."
            )

        for item in commits_recentes:
            sha = item.get("sha")

            if not sha or not re.fullmatch(
                r"[0-9a-fA-F]{40}", sha
            ):
                continue

            try:
                detalhes = consultar_github(
                    cliente,
                    f"{caminho_base}/commits/{sha}",
                )

                commits_analisados.append(
                    analisar_commit(detalhes)
                )

            except (
                httpx.HTTPError,
                RuntimeError,
                ValueError,
            ) as erro:
                logger.warning(
                    "Falha ao analisar commit %s: %s",
                    sha,
                    erro,
                )

                erros.append({
                    "sha": sha,
                    "erro": str(erro),
                })

    resumo = gerar_resumo(commits_analisados)

    return {
        "repositorio": repositorio,
        "resumo": resumo,
        "commits": commits_analisados,
        "termos_recomendacao": (
            gerar_termos_recomendacao(resumo)
        ),
        "erros": erros,
        "observacao": (
            "Monitoramento dos commits recentes "
            "da branch padrão do repositório. "
            "As tecnologias são inferidas pelos "
            "nomes e caminhos dos arquivos."
        ),
    }


if __name__ == "__main__":
    repositorio = (
        sys.argv[1]
        if len(sys.argv) > 1
        else (
            "masteguim/"
            "Modulo5-AGENTE-DE-CURADORIA-"
            "INTELIGENTE-E-TENDENCIAS-TECNOLOGICAS"
        )
    )

    try:
        resultado = monitorar_repositorio(
            repositorio,
            limite=5,
        )

        print(
            json.dumps(
                resultado,
                indent=2,
                ensure_ascii=False,
            )
        )

    except (
        ValueError,
        RuntimeError,
        httpx.HTTPError,
    ) as erro:
        print(
            f"Erro: {erro}",
            file=sys.stderr,
        )
        sys.exit(1)
