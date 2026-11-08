
import json
import logging
import os

import httpx


logger = logging.getLogger(__name__)

URL_ADVISORIES = "https://api.github.com/advisories"

ECOSSISTEMAS = {
    "Python": "pip",
    "FastAPI": "pip",
    "Flask": "pip",
    "Django": "pip",
    "Pydantic": "pip",
    "Uvicorn": "pip",
    "Pytest": "pip",
    "React": "npm",
    "Vite": "npm",
    "Next.js": "npm",
    "JavaScript": "npm",
    "TypeScript": "npm",
    "GitHub Actions": "actions",
}


def identificar_ecossistemas(stack):
    encontrados = set()

    for tecnologia in stack:
        ecossistema = ECOSSISTEMAS.get(tecnologia)

        if ecossistema:
            encontrados.add(ecossistema)

    return sorted(encontrados)


def buscar_avisos_ecossistema(ecossistema, limite=20):
    limite = max(1, min(int(limite), 100))

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "Agente-Curadoria-Modulo5",
    }

    token = os.getenv("GITHUB_TOKEN")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    parametros = {
        "ecosystem": ecossistema,
        "type": "reviewed",
        "sort": "published",
        "direction": "desc",
        "per_page": limite,
    }

    with httpx.Client(
        timeout=20,
        follow_redirects=True,
    ) as cliente:
        resposta = cliente.get(
            URL_ADVISORIES,
            headers=headers,
            params=parametros,
        )

        resposta.raise_for_status()
        return resposta.json()


def formatar_aviso(aviso):
    pacotes = []

    for vulnerabilidade in aviso.get(
        "vulnerabilities", []
    ):
        pacote = vulnerabilidade.get("package") or {}

        pacotes.append({
            "nome": pacote.get("name"),
            "ecossistema": pacote.get("ecosystem"),
            "versoes_afetadas": vulnerabilidade.get(
                "vulnerable_version_range"
            ),
            "primeira_versao_corrigida": vulnerabilidade.get(
                "first_patched_version"
            ),
        })

    cvss = aviso.get("cvss") or {}

    return {
        "id": aviso.get("ghsa_id"),
        "cve": aviso.get("cve_id"),
        "titulo": aviso.get("summary"),
        "descricao": aviso.get("description"),
        "gravidade": aviso.get("severity"),
        "pontuacao_cvss": cvss.get("score"),
        "data_publicacao": aviso.get("published_at"),
        "atualizado_em": aviso.get("updated_at"),
        "link": aviso.get("html_url"),
        "fonte": "GitHub Advisory Database",
        "pacotes_afetados": pacotes,
        "tipo": "aviso_oficial_seguranca",
    }


def consultar_avisos(stack=None, limite=20):
    limite = max(1, min(int(limite), 100))

    if stack is None:
        ecossistemas = ["pip", "npm", "actions"]
    else:
        ecossistemas = identificar_ecossistemas(stack)

    avisos = {}
    erros = []

    for ecossistema in ecossistemas:
        try:
            resultados = buscar_avisos_ecossistema(
                ecossistema,
                limite,
            )

            for resultado in resultados:
                if resultado.get("withdrawn_at"):
                    continue

                identificador = resultado.get("ghsa_id")

                if identificador:
                    avisos[identificador] = formatar_aviso(
                        resultado
                    )

        except (httpx.HTTPError, ValueError) as erro:
            logger.warning(
                "Falha ao consultar %s: %s",
                ecossistema,
                erro,
            )

            erros.append({
                "ecossistema": ecossistema,
                "erro": str(erro),
            })

    lista_avisos = sorted(
        avisos.values(),
        key=lambda aviso: (
            aviso.get("data_publicacao") or ""
        ),
        reverse=True,
    )

    return {
        "total": len(lista_avisos),
        "avisos": lista_avisos[:limite],
        "ecossistemas_consultados": ecossistemas,
        "erros": erros,
        "observacao": (
            "Estes avisos pertencem aos ecossistemas "
            "tecnologicos consultados. Ainda nao foi "
            "confirmado que as dependencias do projeto "
            "estejam vulneraveis."
        ),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    stack_exemplo = [
        "Docker",
        "FastAPI",
        "GitHub Actions",
        "Pydantic",
        "Python",
        "Uvicorn",
    ]

    resultado = consultar_avisos(
        stack=stack_exemplo,
        limite=10,
    )

    print(
        json.dumps(
            resultado,
            indent=2,
            ensure_ascii=False,
        )
    )
