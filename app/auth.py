import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import (
    PyJWKClient,
    PyJWKClientConnectionError,
    PyJWKClientError,
)

M1_BASE_URL = os.getenv(
    "M1_AUTH_URL",
    "https://mod1-auth.whitemeadow-deba1090.brazilsouth.azurecontainerapps.io",
).rstrip("/")
M1_ISSUER = os.getenv("M1_JWT_ISSUER", M1_BASE_URL)
M1_AUDIENCE = os.getenv("M1_JWT_AUDIENCE", "engenharia-software-api")
M1_JWKS_URL = os.getenv(
    "M1_JWKS_URL",
    f"{M1_BASE_URL}/.well-known/jwks.json",
)

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    subject: str
    access_token: str = field(repr=False)
    profile: dict[str, Any] = field(default_factory=dict, repr=False)


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(M1_JWKS_URL, timeout=10)


def _decode_access_token(token: str) -> dict[str, Any]:
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=M1_ISSUER,
            audience=M1_AUDIENCE,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except PyJWKClientConnectionError as erro:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível consultar as chaves do Módulo 1.",
        ) from erro
    except (jwt.PyJWTError, PyJWKClientError) as erro:
        raise HTTPException(
            status_code=401,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from erro

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(
            status_code=401,
            detail="Token sem identificador de usuário válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return claims


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Envie o token do Módulo 1 no cabeçalho Authorization.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = _decode_access_token(credentials.credentials)

    try:
        response = httpx.get(
            f"{M1_BASE_URL}/auth/me",
            headers={
                "Authorization": f"Bearer {credentials.credentials}"
            },
            timeout=10,
        )
    except httpx.RequestError as erro:
        raise HTTPException(
            status_code=503,
            detail="O serviço de identidade está indisponível.",
        ) from erro

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=401,
            detail="A sessão do Módulo 1 não está ativa.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível confirmar a sessão no Módulo 1.",
        )

    try:
        profile = response.json()
    except ValueError as erro:
        raise HTTPException(
            status_code=503,
            detail="O Módulo 1 retornou um perfil inválido.",
        ) from erro

    if not isinstance(profile, dict) or any(
        not isinstance(profile.get(campo), tipo)
        for campo, tipo in (
            ("id", str),
            ("email", str),
            ("display_name", str),
            ("is_active", bool),
        )
    ):
        raise HTTPException(
            status_code=503,
            detail="O Módulo 1 retornou um perfil fora do contrato.",
        )

    return AuthenticatedUser(
        subject=claims["sub"],
        access_token=credentials.credentials,
        profile=profile,
    )


def encaminhar_autenticacao_m1(
    metodo: str,
    caminho: str,
    *,
    dados_formulario: dict[str, str] | None = None,
    dados_json: dict[str, str] | None = None,
    access_token: str | None = None,
) -> Response:
    cabecalhos = {}
    if access_token:
        cabecalhos["Authorization"] = f"Bearer {access_token}"

    try:
        resposta = httpx.request(
            metodo,
            f"{M1_BASE_URL}{caminho}",
            data=dados_formulario,
            json=dados_json,
            headers=cabecalhos,
            timeout=15,
        )
    except httpx.TimeoutException as erro:
        raise HTTPException(
            status_code=504,
            detail="O serviço de identidade excedeu o tempo limite.",
        ) from erro
    except httpx.RequestError as erro:
        raise HTTPException(
            status_code=503,
            detail="O serviço de identidade está indisponível.",
        ) from erro

    if resposta.status_code == 204:
        return Response(status_code=204)

    try:
        conteudo = resposta.json()
    except ValueError as erro:
        raise HTTPException(
            status_code=502,
            detail="O serviço de identidade retornou uma resposta inválida.",
        ) from erro

    return JSONResponse(
        status_code=resposta.status_code,
        content=conteudo,
    )
