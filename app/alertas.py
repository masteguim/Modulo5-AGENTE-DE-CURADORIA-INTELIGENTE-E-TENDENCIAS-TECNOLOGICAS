import re
from datetime import datetime, timezone

from app.database import listar_artigos
from app.curadoria import normalizar


PALAVRAS_CHAVE = {
    "critico": [
        "critical vulnerability",
        "remote code execution",
        "ransomware",
        "zero-day",
        "zero day",
        "actively exploited",
        "vulnerabilidade critica",
        "execucao remota de codigo",
    ],
    "alto": [
        "security vulnerability",
        "security flaw",
        "authentication bypass",
        "privilege escalation",
        "data breach",
        "vulnerabilidade",
        "falha de seguranca",
        "cve-",
    ],
    "medio": [
        "security update",
        "security patch",
        "security advisory",
        "security release",
        "security fix",
        "atualizacao de seguranca",
        "correcao de seguranca",
    ],
}

TECNOLOGIAS = {
    "FastAPI": ["fastapi"],
    "Flask": ["flask"],
    "Django": ["django"],
    "React": ["react", "reactjs"],
    "Vite": ["vite", "vitejs"],
    "Next.js": ["next.js", "nextjs"],
    "Docker": ["docker"],
    "Python": ["python", "pip"],
    "JavaScript": ["javascript", "node.js", "npm"],
    "TypeScript": ["typescript"],
    "GitHub Actions": ["github actions"],
    "Pytest": ["pytest"],
    "Pydantic": ["pydantic"],
    "Qiskit": ["qiskit"],
    "NumPy": ["numpy"],
    "Pandas": ["pandas"],
    "Vue": ["vue", "vuejs"],
    "Angular": ["angular"],
    "Express": ["express", "expressjs"],
}


def contem_expressao(texto, expressao):
    termo = normalizar(expressao)

    padrao = (
        r"(?<!\w)"
        + re.escape(termo)
        + r"(?!\w)"
    )

    return bool(re.search(padrao, texto))


def identificar_gravidade(texto):
    texto = normalizar(texto)

    for gravidade in ("critico", "alto", "medio"):
        palavras = PALAVRAS_CHAVE[gravidade]

        if any(
            contem_expressao(texto, palavra)
            for palavra in palavras
        ):
            return gravidade

    return None


def identificar_tecnologias(texto, stack=None):
    texto = normalizar(texto)
    identificadas = []

    tecnologias = stack or list(TECNOLOGIAS)

    for tecnologia in tecnologias:
        palavras = TECNOLOGIAS.get(
            tecnologia,
            [tecnologia],
        )

        if any(
            contem_expressao(texto, palavra)
            for palavra in palavras
        ):
            identificadas.append(tecnologia)

    return identificadas


def criar_alerta(artigo, stack=None):
    titulo = artigo.get("titulo", "")
    resumo = artigo.get("resumo", "")

    texto = f"{titulo} {resumo}"

    gravidade = identificar_gravidade(texto)

    if gravidade is None:
        return None

    tecnologias = identificar_tecnologias(
        texto,
        stack,
    )

    if stack and not tecnologias:
        return None

    return {
        "titulo": titulo,
        "descricao": resumo[:500],
        "link": artigo.get("link", ""),
        "fonte": artigo.get("fonte", ""),
        "gravidade": gravidade,
        "tecnologias": tecnologias,
        "data_publicacao": artigo.get(
            "data_publicacao"
        ),
        "identificado_em": datetime.now(
            timezone.utc
        ).isoformat(),
        "tipo": "possivel_alerta_seguranca",
    }


def gerar_alertas(stack=None, limite=20):
    limite = max(1, min(int(limite), 100))

    artigos = listar_artigos(500)
    alertas = []

    for artigo in artigos:
        alerta = criar_alerta(artigo, stack)

        if alerta:
            alertas.append(alerta)

    prioridades = {
        "critico": 3,
        "alto": 2,
        "medio": 1,
    }

    alertas.sort(
        key=lambda alerta: (
            prioridades.get(alerta["gravidade"], 0),
            alerta.get("data_publicacao") or "",
        ),
        reverse=True,
    )

    return {
        "total": len(alertas),
        "alertas": alertas[:limite],
        "stack_monitorada": stack or [],
        "artigos_analisados": len(artigos),
    }


if __name__ == "__main__":
    from app.database import inicializar_banco

    inicializar_banco()

    resultado = gerar_alertas()

    print(
        f"Artigos analisados: "
        f"{resultado['artigos_analisados']}"
    )

    print(
        f"Alertas encontrados: "
        f"{resultado['total']}"
    )

    for alerta in resultado["alertas"]:
        print()
        print("Título:", alerta["titulo"])
        print("Gravidade:", alerta["gravidade"])
        print("Fonte:", alerta["fonte"])
        print("Tecnologias:", alerta["tecnologias"])
        print("Link:", alerta["link"])
