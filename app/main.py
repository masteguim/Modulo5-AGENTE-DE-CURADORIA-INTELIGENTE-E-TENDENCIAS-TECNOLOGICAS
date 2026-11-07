import re
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.curadoria import (
    buscar_conteudos,
    coletar_fontes,
    extrair_termos,
    normalizar,
    obter_feed,
    pontuar_artigo,
    selecionar_artigos,
)
from app.github_stack import detectar_stack

app = FastAPI(
    title="Agente de Curadoria Inteligente",
    version="3.0.0",
    description="Curadoria contextual de tendências tecnológicas.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://frontmodulo5-ecaqg8fghzhyeuh2.brazilsouth-01.azurewebsites.net",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

CATEGORIAS = {
    "inteligencia-artificial": {
        "nome": "Inteligência Artificial",
        "termos": [
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "llm",
        ],
    },
    "desenvolvimento": {
        "nome": "Desenvolvimento de Software",
        "termos": [
            "software development",
            "python",
            "javascript",
            "react",
        ],
    },
    "seguranca": {
        "nome": "Segurança",
        "termos": [
            "cybersecurity",
            "vulnerability",
            "security",
            "cve",
        ],
    },
    "devops": {
        "nome": "DevOps e Infraestrutura",
        "termos": [
            "docker",
            "kubernetes",
            "devops",
            "cloud",
        ],
    },
    "computacao-quantica": {
        "nome": "Computação Quântica",
        "termos": [
            "quantum computing",
            "qubit",
            "quantum algorithms",
        ],
    },
}

TERMOS_STACK = {
    "FastAPI": ["fastapi", "python", "asgi"],
    "Flask": ["flask", "python"],
    "Django": ["django", "python"],
    "React": ["react", "reactjs", "react.js"],
    "Vite": ["vite", "vitejs"],
    "Next.js": ["next.js", "nextjs"],
    "Docker": ["docker", "container"],
    "Python": ["python"],
    "JavaScript": ["javascript"],
    "TypeScript": ["typescript"],
    "GitHub Actions": ["github actions", "ci/cd"],
    "Pytest": ["pytest", "python testing"],
    "Qiskit": ["qiskit", "quantum computing"],
    "Pydantic": ["pydantic"],
    "NumPy": ["numpy"],
    "Pandas": ["pandas"],
    "Vue": ["vue", "vuejs"],
    "Angular": ["angular"],
    "Express": ["express", "node.js"],
    "Tailwind CSS": ["tailwind", "tailwindcss"],
}

TERMOS_GERAIS = [
    "software",
    "technology",
    "programming",
    "development",
]

class ConsultaEntrada(BaseModel):
    pergunta: str = Field(min_length=1)


class Artigo(BaseModel):
    titulo: str
    link: str
    fonte: str
    idioma: str
    data_publicacao: str | None = None


class ConsultaResposta(BaseModel):
    pergunta: str
    artigos: list[Artigo]


class FeedResposta(BaseModel):
    artigos: list[Artigo]
    total: int
    categoria: str
    repositorio: str | None = None
    stack_detectada: list[str] = Field(default_factory=list)
    fontes_consultadas: list[str]
    fontes_indisponiveis: list[str]


def termos_repositorio(stack):
    resultado = []

    for tecnologia in stack:
        resultado.extend(
            TERMOS_STACK.get(tecnologia, [tecnologia])
        )

    return list(dict.fromkeys(resultado))


def pontuacao_contextual(artigo, termos, stack):
    conteudo = normalizar(
        artigo["titulo"] + " " + artigo.get("resumo", "")
    )

    pontos = pontuar_artigo(
        artigo,
        extrair_termos(" ".join(termos)),
    )

    for termo in termos_repositorio(stack):
        termo = normalizar(termo)

        if termo and re.search(
            r"(?<!\w)" + re.escape(termo) + r"(?!\w)",
            conteudo,
        ):
            pontos += 6

    return pontos


def gerar_feed(categoria, repositorio):
    if categoria != "geral" and categoria not in CATEGORIAS:
        raise HTTPException(
            status_code=400,
            detail="Categoria inválida.",
        )

    stack = []
    nome_repositorio = None

    if repositorio:
        dados_github = detectar_stack(repositorio)
        stack = dados_github["stack_detectada"]
        nome_repositorio = dados_github["repositorio"]

    termos = list(
        CATEGORIAS.get(categoria, {}).get(
            "termos", TERMOS_GERAIS
        )
    )

    termos.extend(termos_repositorio(stack))
    termos = list(dict.fromkeys(termos))

    consulta = " OR ".join(termos[:6])

    resultado = coletar_fontes(
        consulta or "software development"
    )

    if (
        len(resultado["fontes_indisponiveis"])
        == len(resultado["fontes_consultadas"])
    ):
        raise HTTPException(
            status_code=502,
            detail="Todas as fontes estão indisponíveis.",
        )

    pontuados = []

    for artigo in resultado["artigos"]:
        pontos = pontuacao_contextual(
            artigo, termos, stack
        )

        if categoria != "geral":
            termos_categoria = CATEGORIAS[categoria]["termos"]

            categoria_relevante = pontuar_artigo(
                artigo,
                extrair_termos(" ".join(termos_categoria)),
            )

            if categoria_relevante == 0:
                continue

        if nome_repositorio and pontos == 0:
            continue

        pontuados.append({
            **artigo,
            "_pontuacao": pontos,
        })

    pontuados.sort(
        key=lambda artigo: (
            artigo["_pontuacao"],
            artigo.get("data_publicacao") or "",
        ),
        reverse=True,
    )

    limite = 10 if categoria == "geral" else 5

    artigos = selecionar_artigos(
        pontuados,
        limite,
    )

    return {
        "artigos": artigos,
        "total": len(artigos),
        "categoria": categoria,
        "repositorio": nome_repositorio,
        "stack_detectada": stack,
        "fontes_consultadas": resultado["fontes_consultadas"],
        "fontes_indisponiveis": resultado["fontes_indisponiveis"],
    }


@app.get("/")
def inicio():
    return {
        "aplicacao": "Agente de Curadoria Inteligente",
        "versao": "3.0.0",
        "status": "online",
    }


@app.get("/categorias")
def listar_categorias():
    return {
        "categorias": [
            {"id": chave, "nome": dados["nome"]}
            for chave, dados in CATEGORIAS.items()
        ]
    }


@app.get("/github/stack")
def analisar_repositorio(
    repositorio: str = Query(min_length=3, max_length=200),
):
    return detectar_stack(repositorio)


@app.get(
    "/feed",
    response_model=FeedResposta,
)
def feed(
    categoria: str = "geral",
    repositorio: str | None = None,
):
    return gerar_feed(categoria, repositorio)


@app.post(
    "/consultas",
    response_model=ConsultaResposta,
)
def consultar(dados: ConsultaEntrada):
    resultado = buscar_conteudos(dados.pergunta)

    if (
        len(resultado["fontes_indisponiveis"])
        == len(resultado["fontes_consultadas"])
    ):
        raise HTTPException(
            status_code=502,
            detail="Todas as fontes estão indisponíveis.",
        )

    return {
        "pergunta": dados.pergunta,
        "artigos": resultado["artigos"],
    }
