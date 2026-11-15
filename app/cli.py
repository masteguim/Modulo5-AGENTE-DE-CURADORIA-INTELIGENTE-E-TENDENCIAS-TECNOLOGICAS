import json
import os
from urllib.request import Request, urlopen

token = os.getenv("M1_ACCESS_TOKEN")
if not token:
    raise RuntimeError(
        "Configure M1_ACCESS_TOKEN com seu token de acesso do Módulo 1."
    )

while True:
    pergunta = input("Pergunta (ou 'sair'): ").strip()

    if pergunta.lower() == "sair":
        break

    dados = json.dumps({"pergunta": pergunta}).encode("utf-8")

    requisicao = Request(
        "http://127.0.0.1:8000/consultas",
        data=dados,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    with urlopen(requisicao) as resposta:
        resultado = json.load(resposta)

    print("Resposta:", resultado)
