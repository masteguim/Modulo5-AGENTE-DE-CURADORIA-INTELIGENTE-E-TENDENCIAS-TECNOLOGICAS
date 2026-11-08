
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone

from app.database import inicializar_banco, listar_artigos
from app.curadoria import normalizar


CATEGORIAS = {
    "Inteligência Artificial": [
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "generative ai",
        "llm",
        "openai",
        "inteligencia artificial",
    ],
    "Desenvolvimento": [
        "python",
        "javascript",
        "typescript",
        "react",
        "fastapi",
        "programming",
        "software development",
        "github",
    ],
    "Segurança": [
        "cybersecurity",
        "vulnerability",
        "security",
        "cve",
        "malware",
        "ransomware",
        "seguranca",
    ],
    "DevOps": [
        "docker",
        "kubernetes",
        "devops",
        "cloud",
        "deployment",
        "ci/cd",
    ],
    "Computação Quântica": [
        "quantum computing",
        "quantum computer",
        "qubit",
        "qiskit",
        "computacao quantica",
    ],
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

    return bool(re.search(padrao, texto))


def identificar_categoria(artigo):
    titulo = normalizar(artigo.get("titulo") or "")
    resumo = normalizar(artigo.get("resumo") or "")

    melhor_categoria = "Outros"
    maior_pontuacao = 0

    for categoria, termos in CATEGORIAS.items():
        pontuacao = 0

        for termo in termos:
            if contem_termo(titulo, termo):
                pontuacao += 3

            if contem_termo(resumo, termo):
                pontuacao += 1

        if pontuacao > maior_pontuacao:
            maior_pontuacao = pontuacao
            melhor_categoria = categoria

    return melhor_categoria


def converter_data(valor):
    if not valor:
        return None

    try:
        data = datetime.fromisoformat(
            str(valor).replace("Z", "+00:00")
        )

        if data.tzinfo is None:
            data = data.replace(tzinfo=timezone.utc)

        return data.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


def pontuar_recencia(artigo, agora):
    data = converter_data(
        artigo.get("data_publicacao")
    )

    if data is None:
        data = converter_data(
            artigo.get("coletado_em")
        )

    if data is None:
        return 0.0

    horas = max(
        0.0,
        (agora - data).total_seconds() / 3600,
    )

    return round(
        100 * math.exp(-horas / 168),
        2,
    )


def calcular_pontuacao(
    artigo,
    categoria,
    frequencias,
    agora,
):
    recencia = pontuar_recencia(artigo, agora)

    frequencia = frequencias.get(categoria, 0)

    relevancia = min(
        20,
        math.log1p(frequencia) * 5,
    )

    titulo = normalizar(
        artigo.get("titulo") or ""
    )

    termos = CATEGORIAS.get(categoria, [])

    correspondencias = sum(
        contem_termo(titulo, termo)
        for termo in termos
    )

    contextualizacao = min(
        15,
        correspondencias * 5,
    )

    return round(
        recencia * 0.75
        + relevancia
        + contextualizacao,
        2,
    )


def gerar_em_alta(limite=20, categoria=None):
    limite = max(1, min(int(limite), 100))

    artigos = listar_artigos(500)

    agora = datetime.now(timezone.utc)

    classificados = []

    for artigo in artigos:
        categoria_artigo = identificar_categoria(
            artigo
        )

        classificados.append({
            **artigo,
            "categoria": categoria_artigo,
        })

    frequencias = Counter(
        artigo["categoria"]
        for artigo in classificados
    )

    resultados = []

    for artigo in classificados:
        if (
            categoria
            and categoria != "geral"
            and artigo["categoria"] != categoria
        ):
            continue

        pontuacao = calcular_pontuacao(
            artigo,
            artigo["categoria"],
            frequencias,
            agora,
        )

        resultados.append({
            "titulo": artigo["titulo"],
            "link": artigo["link"],
            "fonte": artigo["fonte"],
            "idioma": artigo.get("idioma", "en"),
            "resumo": artigo.get("resumo", ""),
            "data_publicacao": artigo.get(
                "data_publicacao"
            ),
            "categoria": artigo["categoria"],
            "pontuacao": pontuacao,
        })

    resultados.sort(
        key=lambda artigo: (
            artigo["pontuacao"],
            artigo.get("data_publicacao") or "",
        ),
        reverse=True,
    )

    categorias_disponiveis = [
        {
            "nome": nome,
            "quantidade": quantidade,
        }
        for nome, quantidade in frequencias.most_common()
    ]

    return {
        "total": len(resultados),
        "artigos": resultados[:limite],
        "categorias": categorias_disponiveis,
        "artigos_analisados": len(artigos),
        "atualizado_em": agora.isoformat(),
        "metodo_ranking": (
            "Classificacao por recencia, frequencia "
            "da categoria e correspondencia de termos. "
            "Nao representa popularidade medida "
            "por visualizacoes ou compartilhamentos."
        ),
    }


if __name__ == "__main__":
    inicializar_banco()

    resultado = gerar_em_alta(limite=10)

    print(
        json.dumps(
            resultado,
            ensure_ascii=False,
            indent=2,
        )
    )
