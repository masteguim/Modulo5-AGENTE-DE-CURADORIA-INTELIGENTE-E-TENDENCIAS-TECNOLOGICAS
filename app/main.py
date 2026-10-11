from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title='Agente de Curadoria')

class ConsultaEntrada(BaseModel):
    pergunta: str = Field(min_length = 1)

class ArquivoRelacionado(BaseModel):
    caminho: str
    motivo: str

class ConsultaResposta(BaseModel):
    pergunta: str
    arquivos: list[ArquivoRelacionado]

@app.post("/consultas", response_model=ConsultaResposta)
def consultar(dados: ConsultaEntrada):

    return ConsultaResposta(
        pergunta=dados.pergunta,
        arquivos=[],
    )