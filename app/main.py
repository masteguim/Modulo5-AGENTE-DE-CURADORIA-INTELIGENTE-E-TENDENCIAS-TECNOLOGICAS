from fastapi import FastAPI
from pydantic import BaseModel, Field
from app.curadoria import buscar_artigos

app = FastAPI(title='Agente de Curadoria')

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