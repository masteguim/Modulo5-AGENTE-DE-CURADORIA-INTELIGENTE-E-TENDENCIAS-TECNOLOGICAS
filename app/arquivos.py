from pathlib import Path


EXTENSOES = {".py", ".md", ".txt"}
PASTAS_IGNORADAS = {".git", ".venv", "venv", "__pycache__"}


def listar_arquivos() -> list[Path]:
    raiz = Path(__file__).resolve().parent.parent
    encontrados = []

    for caminho in raiz.rglob("*"):
        partes = caminho.relative_to(raiz).parts

        if (
            caminho.is_file()
            and caminho.suffix.lower() in EXTENSOES
            and not any(pasta in PASTAS_IGNORADAS for pasta in partes)
        ):
            encontrados.append(caminho)

    return sorted(encontrados)