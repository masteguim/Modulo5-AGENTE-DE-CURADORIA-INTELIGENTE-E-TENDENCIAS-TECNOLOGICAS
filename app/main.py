import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.curadoria import (
    buscar_conteudos,
    extrair_termos,
    normalizar,
    pontuar_artigo,
    selecionar_artigos,
)
from app.database import (
    inicializar_banco,
    listar_artigos,
    contar_artigos,
)
from app.github_stack import detectar_stack


@asynccontextmanager
async def lifespan(app: FastAPI):
    inicializar_banco()
    yield


app = FastAPI(
    title="Agente de Curadoria Inteligente",
    version="3.1.0",
    description="Curadoria tecnológica com SQLite e GitHub.",
    lifespan=lifespan,
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
            "inteligencia artificial",
        ],
    },
    "desenvolvimento": {
        "nome": "Desenvolvimento de Software",
        "termos": [
            "software development",
            "python",
            "javascript",
            "react",
            "programming",
        ],
    },
    "seguranca": {
        "nome": "Segurança",
        "termos": [
            "cybersecurity",
            "vulnerability",
            "security",
            "cve",
            "seguranca",
        ],
    },
    "devops": {
        "nome": "DevOps e Infraestrutura",
        "termos": [
            "docker",
            "kubernetes",
            "devops",
            "cloud",
            "container",
        ],
    },
    "computacao-quantica": {
        "nome": "Computação Quântica",
        "termos": [
            "quantum computing",
            "qubit",
            "quantum algorithms",
            "computacao quantica",
        ],
    },
}

TERMOS_STACK = {
    "FastAPI": ["fastapi", "asgi", "python"],
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
    fontes_consultadas: list[str] = Field(default_factory=list)
    fontes_indisponiveis: list[str] = Field(default_factory=list)


def termos_repositorio(stack):
    termos = []

    for tecnologia in stack:
        termos.extend(
            TERMOS_STACK.get(tecnologia, [tecnologia])
        )

    return list(dict.fromkeys(termos))


def corresponde_termo(conteudo, termo):
    termo_normalizado = normalizar(termo)

    if not termo_normalizado:
        return False

    padrao = (
        r"(?<!\w)"
        + re.escape(termo_normalizado)
        + r"(?!\w)"
    )

    return bool(re.search(padrao, conteudo))


def pontuar_recomendacao(artigo, termos, stack):
    conteudo = normalizar(
        artigo.get("titulo", "")
        + " "
        + artigo.get("resumo", "")
    )

    pontos = pontuar_artigo(
        artigo,
        extrair_termos(" ".join(termos)),
    )

    for termo in termos_repositorio(stack):
        if corresponde_termo(conteudo, termo):
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

    artigos_banco = listar_artigos(500)

    if not artigos_banco:
        return {
            "artigos": [],
            "total": 0,
            "categoria": categoria,
            "repositorio": nome_repositorio,
            "stack_detectada": stack,
            "fontes_consultadas": [],
            "fontes_indisponiveis": [],
        }

    termos_categoria = CATEGORIAS.get(
        categoria, {}
    ).get("termos", [])

    termos = termos_categoria + termos_repositorio(stack)

    artigos_pontuados = []

    for artigo in artigos_banco:
        if categoria != "geral":
            conteudo = normalizar(
                artigo.get("titulo", "")
                + " "
                + artigo.get("resumo", "")
            )

            relevante_categoria = any(
                corresponde_termo(conteudo, termo)
                for termo in termos_categoria
            )

            if not relevante_categoria:
                continue

        pontos = pontuar_recomendacao(
            artigo,
            termos,
            stack,
        )

        artigos_pontuados.append({
            **artigo,
            "_pontuacao": pontos,
        })

    artigos_pontuados.sort(
        key=lambda artigo: (
            artigo["_pontuacao"],
            artigo.get("data_publicacao")
            or artigo.get("coletado_em")
            or "",
        ),
        reverse=True,
    )

    limite = 10 if categoria == "geral" else 5

    artigos = selecionar_artigos(
        artigos_pontuados,
        limite,
    )

    fontes = sorted({
        artigo["fonte"]
        for artigo in artigos_banco
    })

    return {
        "artigos": artigos,
        "total": len(artigos),
        "categoria": categoria,
        "repositorio": nome_repositorio,
        "stack_detectada": stack,
        "fontes_consultadas": fontes,
        "fontes_indisponiveis": [],
    }


@app.get("/")
def inicio():
    return {
        "aplicacao": "Agente de Curadoria Inteligente",
        "versao": "3.1.0",
        "status": "online",
        "artigos_armazenados": contar_artigos(),
    }


@app.get("/categorias")
def listar_categorias():
    return {
        "categorias": [
            {
                "id": identificador,
                "nome": dados["nome"],
            }
            for identificador, dados in CATEGORIAS.items()
        ]
    }


@app.get("/github/stack")
def analisar_repositorio(
    repositorio: str = Query(
        min_length=3,
        max_length=200,
    ),
):
    return detectar_stack(repositorio)


@app.get("/artigos")
def artigos_armazenados(
    limite: int = Query(default=50, ge=1, le=500),
):
    return {
        "total_armazenado": contar_artigos(),
        "artigos": listar_artigos(limite),
    }


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
