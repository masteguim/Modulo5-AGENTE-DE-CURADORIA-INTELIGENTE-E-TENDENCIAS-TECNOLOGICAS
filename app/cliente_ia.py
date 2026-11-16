import logging
import os
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MODULO7_API_URL = os.getenv(
    "MODULO7_API_URL",
    (
        "https://mackai-conversas.calmfield-d7c6c49f."
        "brazilsouth.azurecontainerapps.io"
    ),
).rstrip("/")

router = APIRouter(
    prefix="/integracoes/ia",
    tags=["Integração com IA - Módulo 7"],
)


class PerguntaIA(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=20000,
    )
    project_id: UUID | None = None
    conversation_id: UUID | None = None
    profile: Literal[
        "Desenvolvedor",
        "Product Owner",
        "Gerente de Projetos",
    ] = "Desenvolvedor"
    temperature: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
    )


def extrair_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Token de autenticação não informado.",
        )

    partes = authorization.split()

    if (
        len(partes) != 2
        or partes[0].lower() != "bearer"
        or not partes[1]
    ):
        raise HTTPException(
            status_code=401,
            detail="Utilize Authorization: Bearer <token>.",
        )

    return partes[1]


async def consultar_modulo7(
    payload: dict,
    token: str,
) -> dict:
    """Encaminha a pergunta ao assistente do Módulo 7."""

    try:
        async with httpx.AsyncClient(timeout=65.0) as cliente:
            resposta = await cliente.post(
                f"{MODULO7_API_URL}/api/chat",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

    except httpx.TimeoutException as erro:
        logger.warning(
            "Timeout na comunicação com o Módulo 7."
        )
        raise HTTPException(
            status_code=504,
            detail="A IA demorou demais para responder.",
        ) from erro

    except httpx.RequestError as erro:
        logger.error(
            "Erro de conexão com o Módulo 7: %s",
            type(erro).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Não foi possível conectar à API de IA.",
        ) from erro

    if resposta.is_error:
        logger.warning(
            "Módulo 7 retornou HTTP %s",
            resposta.status_code,
        )

        detalhe = "A API de IA recusou a solicitação."

        try:
            corpo = resposta.json()

            if isinstance(corpo, dict):
                mensagem = corpo.get("detail")
                if isinstance(mensagem, str):
                    detalhe = mensagem
        except ValueError:
            pass

        raise HTTPException(
            status_code=resposta.status_code,
            detail=detalhe,
        )

    try:
        dados = resposta.json()
    except ValueError as erro:
        raise HTTPException(
            status_code=502,
            detail="Resposta inválida da API de IA.",
        ) from erro

    if not isinstance(dados, dict):
        raise HTTPException(
            status_code=502,
            detail="Formato inesperado da resposta da IA.",
        )

    return dados


@router.post("/perguntar")
async def perguntar_ia(
    dados: PerguntaIA,
    authorization: str | None = Header(default=None),
):
    """Recebe uma pergunta e a encaminha ao Módulo 7."""

    token = extrair_token(authorization)

    payload = dados.model_dump(
        mode="json",
        exclude_none=True,
    )

    return await consultar_modulo7(
        payload=payload,
        token=token,
    )
