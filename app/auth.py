import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends, HTTPException
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

    return AuthenticatedUser(
        subject=claims["sub"],
        access_token=credentials.credentials,
    )
