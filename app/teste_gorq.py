from dotenv import load_dotenv
from groq import Groq

load_dotenv()
cliente = Groq()

resposta = cliente.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[
        {"role": "user", "content": "Responda em português: conexão funcionando."}
    ],
)

print(resposta.choices[0].message.content)