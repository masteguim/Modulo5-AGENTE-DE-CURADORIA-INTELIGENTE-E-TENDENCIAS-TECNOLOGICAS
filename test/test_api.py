
from fastapi.testclient import TestClient

from app.main import app
from app.recomendacoes import selecionar_recomendacoes

client = TestClient(app)


def criar_artigo(numero=1, idioma="en", fonte="arXiv"):
    return {
        "titulo": f"React and software article {numero}",
        "link": f"https://example.com/artigo-{numero}",
        "fonte": fonte,
        "idioma": idioma,
        "data_publicacao": "2026-11-02T12:00:00+00:00",
    }


def criar_resultado(artigos=None):
    return {
        "artigos": artigos if artigos is not None else [],
        "fontes_consultadas": ["arXiv", "Tecnoblog"],
        "fontes_indisponiveis": [],
    }


def test_inicio(monkeypatch):
    monkeypatch.setattr(
        "app.main.contar_artigos",
        lambda: 0,
    )

    resposta = client.get("/")

    assert resposta.status_code == 200
    assert resposta.json()["versao"] == "3.4.0"
    assert resposta.json()["status"] == "online"
    assert resposta.json()["artigos_armazenados"] == 0


def test_consultar(monkeypatch):
    artigo = criar_artigo()

    def buscar_fake(pergunta):
        assert pergunta == "React"
        return criar_resultado([artigo])

    monkeypatch.setattr(
        "app.main.buscar_conteudos",
        buscar_fake,
    )

    resposta = client.post(
        "/consultas",
        json={"pergunta": "React"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["artigos"] == [artigo]


def test_pergunta_vazia():
    resposta = client.post(
        "/consultas",
        json={"pergunta": ""},
    )

    assert resposta.status_code == 422


def test_consulta_fontes_indisponiveis(monkeypatch):
    def buscar_fake(pergunta):
        assert pergunta == "React"
        return {
            **criar_resultado(),
            "fontes_indisponiveis": [
                "arXiv",
                "Tecnoblog",
            ],
        }

    monkeypatch.setattr(
        "app.main.buscar_conteudos",
        buscar_fake,
    )

    resposta = client.post(
        "/consultas",
        json={"pergunta": "React"},
    )

    assert resposta.status_code == 502


def test_categorias():
    resposta = client.get("/categorias")

    assert resposta.status_code == 200
    assert len(resposta.json()["categorias"]) == 5


def test_feed_geral(monkeypatch):
    artigos = [
        criar_artigo(numero)
        for numero in range(1, 11)
    ]

    def listar_fake(limite):
        assert limite == 500
        return artigos

    monkeypatch.setattr(
        "app.main.listar_artigos",
        listar_fake,
    )

    resposta = client.get("/feed")

    assert resposta.status_code == 200

    dados = resposta.json()

    assert dados["total"] == 10
    assert len(dados["artigos"]) == 10
    assert dados["categoria"] == "geral"
    assert dados["repositorio"] is None


def test_feed_categoria(monkeypatch):
    artigos = [
        criar_artigo(numero)
        for numero in range(1, 11)
    ]

    def listar_fake(limite):
        assert limite == 500
        return artigos

    monkeypatch.setattr(
        "app.main.listar_artigos",
        listar_fake,
    )

    resposta = client.get(
        "/feed?categoria=desenvolvimento"
    )

    assert resposta.status_code == 200

    dados = resposta.json()

    assert dados["total"] == 5
    assert len(dados["artigos"]) == 5
    assert dados["categoria"] == "desenvolvimento"


def test_categoria_invalida():
    resposta = client.get(
        "/feed?categoria=desconhecida"
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == (
        "Categoria inválida."
    )


def test_detectar_stack(monkeypatch):
    def detectar_fake(repositorio):
        assert repositorio == "usuario/projeto"

        return {
            "repositorio": repositorio,
            "stack_detectada": ["React", "Docker"],
            "arquivos_analisados": [
                "package.json",
                "Dockerfile",
            ],
        }

    monkeypatch.setattr(
        "app.main.detectar_stack",
        detectar_fake,
    )

    resposta = client.get(
        "/github/stack?repositorio=usuario/projeto"
    )

    assert resposta.status_code == 200

    dados = resposta.json()

    assert dados["repositorio"] == "usuario/projeto"
    assert dados["stack_detectada"] == [
        "React",
        "Docker",
    ]


def test_limite_geral():
    artigos = [
        criar_artigo(numero)
        for numero in range(1, 21)
    ]

    resultado = selecionar_recomendacoes(
        artigos,
        limite=10,
    )

    assert len(resultado) == 10


def test_limite_categoria():
    artigos = [
        criar_artigo(numero)
        for numero in range(1, 21)
    ]

    resultado = selecionar_recomendacoes(
        artigos,
        limite=5,
        categoria="desenvolvimento",
    )

    assert len(resultado) == 5


def test_prioridade_da_stack():
    artigos = [
        {
            **criar_artigo(1),
            "titulo": "Notícias gerais de tecnologia",
        },
        {
            **criar_artigo(2),
            "titulo": "React updates for developers",
        },
    ]

    resultado = selecionar_recomendacoes(
        artigos,
        limite=2,
        stack=["React"],
    )

    assert resultado[0]["titulo"] == (
        "React updates for developers"
    )
