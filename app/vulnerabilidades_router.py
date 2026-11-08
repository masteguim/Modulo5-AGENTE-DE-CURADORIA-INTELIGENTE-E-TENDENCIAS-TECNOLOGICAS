
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.analise_vulnerabilidades import analisar_repositorio
from app.dependencias import normalizar_repositorio


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/github",
    tags=["Segurança do GitHub"],
)


@router.get("/vulnerabilidades")
async def consultar_vulnerabilidades(
    repositorio: str = Query(
        min_length=3,
        max_length=200,
        description="Repositório no formato usuario/projeto",
    ),
):
    try:
        repositorio_normalizado = normalizar_repositorio(
            repositorio
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro

    try:
        resultado = await run_in_threadpool(
            analisar_repositorio,
            repositorio_normalizado,
        )

    except httpx.HTTPStatusError as erro:
        logger.warning(
            "Erro HTTP ao consultar GitHub: %s",
            erro,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Não foi possível consultar os dados "
                "do repositório no GitHub."
            ),
        ) from erro

    except (httpx.RequestError, RuntimeError) as erro:
        logger.exception(
            "Erro na análise de vulnerabilidades: %s",
            erro,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Falha na comunicação com os serviços "
                "de análise de vulnerabilidades."
            ),
        ) from erro

    return resultado
