from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt as jwt_lib
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import auth
from app.auth import AuthenticatedUser, get_current_user
from app.integracoes import perguntar_ao_modulo7


def test_missing_bearer_is_unauthorized():
    with pytest.raises(HTTPException) as erro:
        get_current_user(None)

    assert erro.value.status_code == 401


def test_valid_token_requires_active_module1_session(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(
        auth,
        "_decode_access_token",
        lambda _token: {"sub": "usuario-42"},
    )

    def obter_sessao(url, headers, timeout):
        chamadas.update(url=url, headers=headers, timeout=timeout)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(auth.httpx, "get", obter_sessao)

    usuario = get_current_user(
        HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="token-privado-de-teste",
        )
    )

    assert usuario.subject == "usuario-42"
    assert chamadas["headers"]["Authorization"] == (
        "Bearer token-privado-de-teste"
    )


def test_access_token_requires_rs256_issuer_and_audience(monkeypatch):
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    monkeypatch.setattr(
        auth,
        "_jwks_client",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(
                key=private_key.public_key()
            )
        ),
    )
    claims = {
        "sub": "usuario-42",
        "iss": auth.M1_ISSUER,
        "aud": auth.M1_AUDIENCE,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }

    token = jwt_lib.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    assert auth._decode_access_token(token)["sub"] == "usuario-42"

    token_hs = jwt_lib.encode(
        claims,
        "segredo-de-teste-com-tamanho-suficiente-para-hmac",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as erro:
        auth._decode_access_token(token_hs)
    assert erro.value.status_code == 401

    token_wrong_audience = jwt_lib.encode(
        {**claims, "aud": "audience-errada"},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    with pytest.raises(HTTPException) as erro:
        auth._decode_access_token(token_wrong_audience)
    assert erro.value.status_code == 401


def test_m7_receives_user_token_and_project_context(monkeypatch):
    from uuid import UUID

    chamadas = {}

    def enviar(url, headers, json, timeout):
        chamadas.update(
            url=url,
            headers=headers,
            json=json,
            timeout=timeout,
        )
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "conversation_id": "m7-chat-1",
                "message": {"content": "Resposta"},
            },
        )

    monkeypatch.setattr("app.integracoes.httpx.post", enviar)
    usuario = AuthenticatedUser(
        subject="usuario-42",
        access_token="bearer-42",
    )
    project_id = UUID("7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01")

    resultado = perguntar_ao_modulo7(
        usuario=usuario,
        pergunta="Analise a arquitetura",
        project_id=project_id,
        conversation_id=None,
        profile="Desenvolvedor",
        temperature=0.4,
    )

    assert resultado["conversation_id"] == "m7-chat-1"
    assert chamadas["headers"]["Authorization"] == "Bearer bearer-42"
    assert chamadas["json"]["project_id"] == str(project_id)
    assert chamadas["json"]["conversation_id"] is None
    assert chamadas["timeout"] == 65
