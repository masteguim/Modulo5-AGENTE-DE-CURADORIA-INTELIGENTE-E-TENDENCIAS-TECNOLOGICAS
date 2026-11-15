import os
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException

from app.auth import M1_BASE_URL, AuthenticatedUser

M7_BASE_URL = os.getenv(
    "M7_BASE_URL",
    "https://mackai-conversas.calmfield-d7c6c49f.brazilsouth.azurecontainerapps.io",
).rstrip("/")


def verificar_acesso_projeto(
    usuario: AuthenticatedUser,
    project_id: UUID,
) -> None:
    try:
        response = httpx.get(
            f"{M1_BASE_URL}/projects/{project_id}/access/v2",
            headers={
                "Authorization": f"Bearer {usuario.access_token}"
            },
            timeout=10,
        )
    except httpx.RequestError as erro:
        raise HTTPException(
            status_code=503,
            detail="O serviço de projetos está indisponível.",
        ) from erro

    if response.status_code == 200:
        return
    if response.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="A sessão do Módulo 1 não está ativa.",
        )
    if response.status_code in (403, 404):
        raise HTTPException(
            status_code=response.status_code,
            detail="Projeto inexistente ou sem acesso para esta conta.",
        )
    raise HTTPException(
        status_code=503,
        detail="Não foi possível verificar o acesso ao projeto.",
    )


def perguntar_ao_modulo7(
    usuario: AuthenticatedUser,
    pergunta: str,
    project_id: UUID | None,
    conversation_id: str | None,
    profile: str,
    temperature: float,
) -> dict[str, Any]:
    request_id = str(uuid4())
    payload = {
        "message": pergunta,
        "project_id": str(project_id) if project_id else None,
        "conversation_id": conversation_id,
        "profile": profile,
        "temperature": temperature,
    }

    try:
        response = httpx.post(
            f"{M7_BASE_URL}/api/chat",
            headers={
                "Authorization": f"Bearer {usuario.access_token}",
                "X-Request-ID": request_id,
            },
            json=payload,
            timeout=65,
        )
    except httpx.TimeoutException as erro:
        raise HTTPException(
            status_code=504,
            detail=(
                "O Módulo 7 excedeu o tempo limite. "
                "A pergunta não foi repetida automaticamente."
            ),
        ) from erro
    except httpx.RequestError as erro:
        raise HTTPException(
            status_code=503,
            detail="O assistente do Módulo 7 está indisponível.",
        ) from erro

    if response.status_code >= 400:
        if response.status_code in (401, 404, 422, 429, 503):
            try:
                body = response.json()
            except ValueError:
                body = {}
            detail = (
                body.get("detail")
                if isinstance(body, dict)
                else None
            )
            if not isinstance(detail, str):
                detail = "O Módulo 7 recusou a solicitação."
            raise HTTPException(
                status_code=response.status_code,
                detail=detail,
            )
        raise HTTPException(
            status_code=502,
            detail="O Módulo 7 não conseguiu processar a pergunta.",
        )

    try:
        result = response.json()
    except ValueError as erro:
        raise HTTPException(
            status_code=502,
            detail="O Módulo 7 retornou uma resposta inválida.",
        ) from erro

    message = result.get("message") if isinstance(result, dict) else None
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("conversation_id"), str)
        or not isinstance(message, dict)
        or not isinstance(message.get("content"), str)
    ):
        raise HTTPException(
            status_code=502,
            detail="O Módulo 7 retornou uma resposta fora do contrato.",
        )

    return result
