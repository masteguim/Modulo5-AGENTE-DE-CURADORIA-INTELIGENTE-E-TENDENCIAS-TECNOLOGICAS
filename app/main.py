from fastapi import FastAPI
from pydantic import BaseModel, Field
from app.curadoria import buscar_artigos
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title='Agente de Curadoria')
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
    pergunta: str = Field(min_length = 1)

class Artigo(BaseModel):
    titulo: str
    link: str

class ConsultaResposta(BaseModel):
    pergunta: str
    artigos: list[Artigo]

@app.post("/consultas", response_model=ConsultaResposta)
def consultar(dados: ConsultaEntrada):

    return ConsultaResposta(
        pergunta=dados.pergunta,
        artigos=buscar_artigos(dados.pergunta),
    )
