
import base64
import json
import os
import re
import sys
from urllib.parse import quote, urlparse

import httpx


GITHUB_API = "https://api.github.com"

ARQUIVOS_SUPORTADOS = [
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
]

GRUPOS_NPM = {
    "dependencies": "producao",
    "devDependencies": "desenvolvimento",
    "optionalDependencies": "opcional",
    "peerDependencies": "peer",
}


def normalizar_nome(nome, ecossistema):
    if ecossistema == "pip":
        return re.sub(
            r"[-_.]+",
            "-",
            nome.strip(),
        ).lower()

    return nome.strip().lower()


def normalizar_repositorio(repositorio):
    repositorio = repositorio.strip()

    if repositorio.startswith(
        ("https://", "http://")
    ):
        url = urlparse(repositorio)

        if (
            url.hostname != "github.com"
            or url.username
            or url.password
            or url.port
        ):
            raise ValueError(
                "A URL deve pertencer ao github.com."
            )

        repositorio = url.path.strip("/")

    repositorio = repositorio.removesuffix(".git")
    partes = repositorio.strip("/").split("/")

    if len(partes) != 2:
        raise ValueError(
            "Informe o repositório como usuario/projeto."
        )

    padrao = r"^[A-Za-z0-9_.-]+$"

    if not all(
        re.fullmatch(padrao, parte)
        for parte in partes
    ):
        raise ValueError(
            "Nome de repositório inválido."
        )

    if any(parte in (".", "..") for parte in partes):
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
        headers=headers,
        timeout=20,
        follow_redirects=False,
    )


def obter_arquivo(cliente, repositorio, caminho):
    repositorio_url = "/".join(
        quote(parte, safe="")
        for parte in repositorio.split("/")
    )

    caminho_url = "/".join(
        quote(parte, safe="")
        for parte in caminho.split("/")
    )

    url = (
        f"{GITHUB_API}/repos/"
        f"{repositorio_url}/contents/{caminho_url}"
    )

    resposta = cliente.get(url)

    if resposta.status_code == 404:
        return None

    resposta.raise_for_status()

    dados = resposta.json()

    if (
        not isinstance(dados, dict)
        or dados.get("type") != "file"
    ):
        return None

    conteudo = dados.get("content", "")
    codificacao = dados.get("encoding")

    if codificacao != "base64":
        raise ValueError(
            f"Codificação não suportada: {caminho}"
        )

    texto = base64.b64decode(
        conteudo,
        validate=False,
    ).decode("utf-8-sig")

    return texto


def extrair_versao_exata(especificacao):
    especificacao = especificacao.strip()

    resultado = re.fullmatch(
        r"==\s*([0-9][A-Za-z0-9.!+_-]*)",
        especificacao,
    )

    if resultado and "*" not in resultado.group(1):
        return resultado.group(1)

    return None


def analisar_requirements(texto, arquivo):
    dependencias = []

    for numero_linha, linha in enumerate(
        texto.splitlines(),
        start=1,
    ):
        linha = linha.strip()

        if not linha or linha.startswith("#"):
            continue

        if linha.startswith(("-", "git+", "http")):
            continue

        linha = linha.split(" #", 1)[0].strip()

        principal = linha.split(";", 1)[0].strip()

        resultado = re.match(
            r"^([A-Za-z0-9][A-Za-z0-9._-]*)"
            r"(?:\[[^\]]+\])?"
            r"\s*(.*)$",
            principal,
        )

        if not resultado:
            continue

        nome = resultado.group(1)
        especificacao = resultado.group(2).strip()

        if especificacao and not re.match(
            r"^(==|!=|>=|<=|~=|>|<)",
            especificacao,
        ):
            continue

        versao = extrair_versao_exata(
            especificacao
        )

        dependencias.append({
            "nome": nome,
            "nome_normalizado": normalizar_nome(
                nome,
                "pip",
            ),
            "ecossistema": "pip",
            "especificacao": especificacao or "*",
            "versao_exata": versao,
            "versao_fixa": versao is not None,
            "grupo": (
                "desenvolvimento"
                if "dev" in arquivo
                else "producao"
            ),
            "arquivo": arquivo,
            "linha": numero_linha,
        })

    return dependencias


def analisar_package_json(texto, arquivo):
    dados = json.loads(texto)
    dependencias = []

    for campo, grupo in GRUPOS_NPM.items():
        pacotes = dados.get(campo, {})

        if not isinstance(pacotes, dict):
            continue

        for nome, especificacao in pacotes.items():
            especificacao = str(
                especificacao
            ).strip()

            versao = (
                especificacao
                if re.fullmatch(
                    r"\d+\.\d+\.\d+"
                    r"(?:-[A-Za-z0-9.-]+)?"
                    r"(?:\+[A-Za-z0-9.-]+)?",
                    especificacao,
                )
                else None
            )

            dependencias.append({
                "nome": nome,
                "nome_normalizado": normalizar_nome(
                    nome,
                    "npm",
                ),
                "ecossistema": "npm",
                "especificacao": especificacao,
                "versao_exata": versao,
                "versao_fixa": versao is not None,
                "grupo": grupo,
                "arquivo": arquivo,
                "linha": None,
            })

    return dependencias


def analisar_arquivo(caminho, conteudo):
    if caminho.endswith(".json"):
        return analisar_package_json(
            conteudo,
            caminho,
        )

    return analisar_requirements(
        conteudo,
        caminho,
    )


def identificar_dependencias(repositorio):
    repositorio = normalizar_repositorio(
        repositorio
    )

    dependencias = []
    arquivos_encontrados = []
    arquivos_ausentes = []
    erros = []

    with criar_cliente() as cliente:
        for caminho in ARQUIVOS_SUPORTADOS:
            try:
                conteudo = obter_arquivo(
                    cliente,
                    repositorio,
                    caminho,
                )

                if conteudo is None:
                    arquivos_ausentes.append(
                        caminho
                    )
                    continue

                encontrados = analisar_arquivo(
                    caminho,
                    conteudo,
                )

                dependencias.extend(encontrados)

                arquivos_encontrados.append(
                    caminho
                )

            except (
                httpx.HTTPError,
                ValueError,
                UnicodeError,
                json.JSONDecodeError,
            ) as erro:
                erros.append({
                    "arquivo": caminho,
                    "erro": str(erro),
                })

    dependencias_unicas = {}
    for dependencia in dependencias:
        chave = (
            dependencia["ecossistema"],
            dependencia["nome_normalizado"],
            dependencia["grupo"],
        )

        dependencias_unicas[chave] = dependencia

    resultado = list(
        dependencias_unicas.values()
    )

    resultado.sort(
        key=lambda dependencia: (
            dependencia["ecossistema"],
            dependencia["nome_normalizado"],
        )
    )

    return {
        "repositorio": repositorio,
        "total": len(resultado),
        "dependencias": resultado,
        "arquivos_encontrados": arquivos_encontrados,
        "arquivos_ausentes": arquivos_ausentes,
        "erros": erros,
        "observacao": (
            "As versoes representam declaracoes "
            "nos arquivos do repositorio, nao "
            "necessariamente as versoes instaladas."
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
        resultado = identificar_dependencias(
            repositorio
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
        httpx.HTTPError,
    ) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        sys.exit(1)
