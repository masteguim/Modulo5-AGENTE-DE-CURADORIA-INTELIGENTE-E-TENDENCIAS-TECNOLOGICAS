
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.curadoria import (
    buscar_conteudos,
    obter_feed,
)

app = FastAPI(
    title="Agente de Curadoria Inteligente",
    version="2.3.0",
    description="Curadoria de conteúdo tecnológico em português e inglês.",
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
    fontes_consultadas: list[str]
    fontes_indisponiveis: list[str]


@app.get("/")
def inicio():
    return {
        "aplicacao": "Agente de Curadoria Inteligente",
        "versao": "2.3.0",
        "status": "online",
    }


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

    return ConsultaResposta(
        pergunta=dados.pergunta,
        artigos=resultado["artigos"],
    )


@app.get(
    "/feed",
    response_model=FeedResposta,
)
def feed():
    resultado = obter_feed()

    if (
        len(resultado["fontes_indisponiveis"])
        == len(resultado["fontes_consultadas"])
    ):
        raise HTTPException(
            status_code=502,
            detail="Todas as fontes estão indisponíveis.",
        )

    return FeedResposta(**resultado)
