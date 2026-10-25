import json
from urllib.request import Request, urlopen


while True:
    pergunta = input("Pergunta (ou 'sair'): ").strip()

    if pergunta.lower() == "sair":
        break

    dados = json.dumps({"pergunta": pergunta}).encode("utf-8")

    requisicao = Request(
        "http://127.0.0.1:8000/consultas",
        data=dados,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(requisicao) as resposta:
        resultado = json.load(resposta)

    print("Resposta:", resultado)
