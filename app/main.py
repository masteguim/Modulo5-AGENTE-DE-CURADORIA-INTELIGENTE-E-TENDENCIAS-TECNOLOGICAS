import urllib.error
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.curadoria import buscar_conteudos
from app.recomendacoes import (
    CATEGORIAS,
    analisar_repositorio,
    obter_recomendacoes,
)

app = FastAPI(
    title="Agente de Curadoria Inteligente",
    version="2.4.0",
    description="Curadoria tecnológica personalizada pela stack GitHub.",
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
    stack_detectada: list[str]
    fontes_consultadas: list[str]
    fontes_indisponiveis: list[str]


class StackResposta(BaseModel):
    repositorio: str
    stack_detectada: list[str]
    arquivos_analisados: list[str]


@app.get("/")
def inicio():
    return {
        "aplicacao": "Agente de Curadoria Inteligente",
        "versao": "2.4.0",
        "status": "online",
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


@app.get(
    "/github/stack",
    response_model=StackResposta,
)
def detectar_stack(
    repositorio: str = Query(
        min_length=3,
        max_length=200,
    ),
):
    try:
        return analisar_repositorio(
            repositorio
        )
    except ValueError as erro:
        raise HTTPException(
            status_code=422,
            detail=str(erro),
        ) from erro
    except urllib.error.HTTPError as erro:
        codigo = 404 if erro.code == 404 else 502
        raise HTTPException(
            status_code=codigo,
            detail="Não foi possível consultar o repositório GitHub.",
        ) from erro
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as erro:
        raise HTTPException(
            status_code=502,
            detail="GitHub temporariamente indisponível.",
        ) from erro


@app.post(
    "/consultas",
    response_model=ConsultaResposta,
)
def consultar(dados: ConsultaEntrada):
    resultado = buscar_conteudos(
        dados.pergunta
    )

    if (
        len(resultado["fontes_indisponiveis"])
        == len(resultado["fontes_consultadas"])
    ):
        raise HTTPException(
            status_code=502,
            detail="Todas as fontes estão indisponíveis.",
        )

    return ConsultaResposta(
        pergunta=dados.pergunta,
        artigos=resultado["artigos"],
    )


@app.get(
    "/feed",
    response_model=FeedResposta,
)
def feed(
    categoria: str | None = None,
    repositorio: str | None = None,
):
    try:
        resultado = obter_recomendacoes(
            categoria=categoria,
            repositorio=repositorio,
        )
    except ValueError as erro:
        raise HTTPException(
            status_code=422,
            detail=str(erro),
        ) from erro
    except urllib.error.HTTPError as erro:
        codigo = 404 if erro.code == 404 else 502
        raise HTTPException(
            status_code=codigo,
            detail="Erro ao consultar o GitHub.",
        ) from erro
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as erro:
        raise HTTPException(
            status_code=502,
            detail="GitHub temporariamente indisponível.",
        ) from erro

    if (
        len(resultado["fontes_indisponiveis"])
        == len(resultado["fontes_consultadas"])
    ):
        raise HTTPException(
            status_code=502,
            detail="Todas as fontes de notícias estão indisponíveis.",
        )

    return FeedResposta(**resultado)
