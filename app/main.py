
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.curadoria import buscar_conteudos, obter_feed

LIMITE_ARTIGOS = 5

app = FastAPI(
    title="Agente de Curadoria Inteligente",
    version="2.2.0",
    description="Curadoria de artigos, notícias e tendências tecnológicas.",
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
    data_publicacao: str | None = None


class ConsultaResposta(BaseModel):
    pergunta: str
    artigos: list[Artigo]


class FeedResposta(BaseModel):
    artigos: list[Artigo]
    total: int
    fontes_consultadas: list[str]
    fontes_indisponiveis: list[str]


def selecionar_artigos_feed(artigos):
    selecionados = []
    fontes_utilizadas = set()
    links_utilizados = set()

    for artigo in artigos:
        if len(selecionados) >= LIMITE_ARTIGOS:
            break

        fonte = artigo["fonte"]
        link = artigo["link"]

        if fonte not in fontes_utilizadas:
            selecionados.append(artigo)
            fontes_utilizadas.add(fonte)
            links_utilizados.add(link)

    for artigo in artigos:
        if len(selecionados) >= LIMITE_ARTIGOS:
            break

        if artigo["link"] not in links_utilizados:
            selecionados.append(artigo)
            links_utilizados.add(artigo["link"])

    return sorted(
        selecionados,
        key=lambda artigo: artigo.get("data_publicacao") or "",
        reverse=True,
    )


@app.get("/")
def inicio():
    return {
        "aplicacao": "Agente de Curadoria Inteligente",
        "versao": "2.2.0",
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

    artigos = resultado["artigos"][:LIMITE_ARTIGOS]

    return ConsultaResposta(
        pergunta=dados.pergunta,
        artigos=artigos,
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

    artigos = selecionar_artigos_feed(
        resultado["artigos"]
    )

    return FeedResposta(
        artigos=artigos,
        total=len(artigos),
        fontes_consultadas=resultado["fontes_consultadas"],
        fontes_indisponiveis=resultado["fontes_indisponiveis"],
    )
