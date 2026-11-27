# Módulo 5 — Agente de Curadoria Inteligente e Tendências Tecnológicas | Backend

API REST desenvolvida em **Python e FastAPI** para o Módulo 5 do projeto de Engenharia de Software. O serviço reúne conteúdos sobre tecnologia, gera feeds e tendências, analisa a stack de repositórios GitHub e persiste informações em PostgreSQL.

## Links

- **API publicada (Azure App Service):** https://agente-tendencias-tecnologicas-fyd3bzerc9a2cqcu.chilecentral-01.azurewebsites.net
- **Swagger / documentação interativa:** https://agente-tendencias-tecnologicas-fyd3bzerc9a2cqcu.chilecentral-01.azurewebsites.net/docs
- **Frontend publicado:** https://frontmodulo5-ecaqg8fghzhyeuh2.brazilsouth-01.azurewebsites.net/
- **Repositório do frontend:** https://github.com/Aruak-Malta/Modulo5-CURADORIA-INTELIGENTE-E-TENDENCIAS-TECNOLOGICAS

> A disponibilidade dos serviços publicados depende do status e dos limites do respectivo plano de hospedagem.

## Funcionalidades

- **Curadoria de conteúdos:** consulta e seleção de artigos e notícias de fontes externas de tecnologia.
- **Feed por categoria:** seleção e ranqueamento de publicações conforme assunto e contexto tecnológico.
- **Em Alta:** classificação e apresentação de conteúdos em destaque.
- **GitHub:** identificação da stack, leitura de dependências e análise de alterações recentes em repositórios.
- **Recomendações:** associação de publicações relevantes às tecnologias encontradas nos repositórios.
- **Alertas e segurança:** recursos de monitoramento e análise de vulnerabilidades.
- **Persistência:** artigos, usuários referenciados externamente, conversas, conteúdos, integrações GitHub, tecnologias e recomendações.
- **Integrações entre módulos:** autenticação delegada ao Módulo 1, verificação de acesso a projetos e integração do assistente com o Módulo 7.

**Delimitação arquitetural:** o chat/assistente de IA pertence a outro módulo (Módulo 7). O Módulo 5 disponibiliza funcionalidades de curadoria e integrações; o sistema completo prevê um microfrontend integrador para conectar os módulos.

## Tecnologias

| Camada | Tecnologia |
|---|---|
| API REST | FastAPI, Pydantic |
| Servidor ASGI | Uvicorn, Gunicorn |
| Persistência | PostgreSQL, SQLAlchemy, psycopg 3 |
| Migrações | Alembic |
| Integrações HTTP | HTTPX e APIs externas |
| Autenticação | JWT, JWKS; identidade delegada ao Módulo 1 |
| Qualidade | Pytest, Ruff, GitHub Actions |
| Hospedagem | Azure App Service |
| Banco gerenciado | Neon PostgreSQL |

## Arquitetura simplificada

```text
Frontend React/Vite (Módulo 5)
             |
             | HTTP / JSON
             v
      Backend FastAPI (Módulo 5)
       |       |        |
       |       |        +-- GitHub e fontes externas
       |       +----------- PostgreSQL (Neon)
       +------------------- Integrações: Módulo 1 / projetos / Módulo 7

Microfrontend integrador do sistema completo: conecta os módulos.
```

## Estrutura do projeto

```text
.
├── app/
│   ├── main.py                 # Aplicação FastAPI, rotas e integrações
│   ├── database.py             # Conexão e operações no PostgreSQL
│   ├── models.py               # Modelos SQLAlchemy
│   ├── schemas.py              # Esquemas de dados
│   ├── curadoria.py            # Curadoria de conteúdos
│   ├── em_alta.py              # Conteúdos em destaque
│   ├── github_stack.py         # Identificação de tecnologias GitHub
│   ├── monitoramento.py        # Monitoramento de alterações
│   ├── recomendacoes.py        # Recomendações contextuais
│   ├── auth.py                 # Integração de autenticação
│   ├── integracoes.py          # Comunicação entre módulos
│   └── vulnerabilidades_router.py
├── migrations/                 # Migrações do Alembic
├── test/                       # Testes automatizados
├── .github/workflows/          # Pipeline CI/CD
├── alembic.ini
├── requirements.txt
├── requirements-dev.txt
└── Dockerfile
```

## Requisitos

- Python 3.12 ou versão compatível com as dependências do projeto;
- PostgreSQL acessível (por exemplo, banco Neon ou instância local);
- Git;
- Credenciais de serviços externos quando exigidas pelas funcionalidades utilizadas.

## Executar localmente (Linux)

Clone o repositório e acesse a pasta:

```bash
git clone https://github.com/masteguim/Modulo5-AGENTE-DE-CURADORIA-INTELIGENTE-E-TENDENCIAS-TECNOLOGICAS.git
cd Modulo5-AGENTE-DE-CURADORIA-INTELIGENTE-E-TENDENCIAS-TECNOLOGICAS
```

> O desenvolvimento e as últimas correções foram realizados na branch `branchlucas`. Para reproduzir essa versão, execute `git switch branchlucas` após clonar.

Crie o ambiente virtual e instale as dependências:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Crie um arquivo `.env` na raiz e configure a **sua própria** conexão PostgreSQL:

```dotenv
DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@HOST_DO_NEON/neondb?sslmode=require
```

Use a **connection string direta** fornecida pelo Neon, com `postgresql+psycopg://`. Nunca publique credenciais reais no GitHub.

Para preparar **um banco novo e vazio**, aplique as migrações:

```bash
python -m alembic upgrade head
python -m alembic current
```

Se estiver usando um banco Neon já migrado, **não restaure nem recrie as tabelas**: basta configurar `DATABASE_URL` corretamente.

Inicie a aplicação:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Acesse http://127.0.0.1:8000/docs.

### Execução com Gunicorn

```bash
gunicorn -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 app.main:app
```

## Principais endpoints

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/` | Status e quantidade de artigos armazenados |
| `GET` | `/artigos` | Consultar artigos persistidos |
| `GET` | `/categorias` | Listar categorias de curadoria |
| `GET` | `/feed` | Feed por categoria e, opcionalmente, repositório |
| `GET` | `/em-alta` | Conteúdos em destaque |
| `GET` | `/alertas` | Alertas relacionados à stack tecnológica |
| `GET` | `/github/stack` | Identificar tecnologias de um repositório |
| `GET` | `/github/alteracoes` | Consultar alterações recentes no GitHub |
| `POST` | `/github/repositorios` | Salvar integração GitHub do usuário |
| `GET` | `/github/repositorios` | Listar integrações GitHub do usuário |
| `GET` | `/github/recomendacoes` | Consultar recomendações do usuário |
| `POST` | `/consultas` | Consultar conteúdos e registrar interação |
| `POST` | `/assistente` | Integrar consulta ao assistente de outro módulo |
| `GET` | `/conversas` | Listar histórico de conversas |
| `GET` | `/conversas/{chat_id}` | Consultar conversa específica |
| `GET/POST` | `/projetos/{project_id}/repositorios` | Listar ou registrar repositórios de projeto |
| `GET` | `/projetos/{project_id}/recomendacoes` | Recomendações associadas ao projeto |
| `POST` | `/auth/login` | Encaminhar login ao Módulo 1 |
| `POST` | `/auth/mfa/verify` | Validar segundo fator |
| `POST` | `/auth/refresh` | Renovar token |
| `POST` | `/auth/logout` | Encerrar sessão |
| `GET` | `/auth/session` | Consultar sessão autenticada |

Algumas rotas exigem um JWT válido e, no caso de projetos, autorização de acesso. Consulte `/docs` para verificar parâmetros e esquemas atualizados.

### Exemplo de consulta pública

```bash
curl "http://127.0.0.1:8000/artigos?limite=5"
```

### Exemplo de análise de stack

```bash
curl -G "http://127.0.0.1:8000/github/stack" \
  --data-urlencode "repositorio=facebook/react"
```

## Banco de dados

O ambiente de hospedagem utiliza **Neon PostgreSQL**, com conexão definida pela variável `DATABASE_URL`. O schema é versionado com Alembic e contém tabelas para artigos, usuários, chats, conteúdos, integrações GitHub, tecnologias e recomendações.

A autenticação de usuários não é implementada diretamente no banco deste módulo: a identidade é delegada ao Módulo 1.

## Testes e qualidade

Para instalar as dependências de desenvolvimento:

```bash
python -m pip install -r requirements-dev.txt
```

Executar validações:

```bash
python -m compileall -q app
python -m ruff check app test
python -m pytest -q
```

O GitHub Actions executa verificações e o fluxo de publicação no Azure conforme a configuração do repositório.

## Publicação no Azure

A aplicação está configurada para execução com Python, Gunicorn e Uvicorn. O comando utilizado no App Service é:

```bash
gunicorn -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 app.main:app
```

No App Service, configure `DATABASE_URL` em **Settings → Environment variables** usando a URL do Neon com o driver `postgresql+psycopg`. O frontend publicado deve estar autorizado na lista de origens CORS do backend.

**Atenção aos custos:** o plano Azure App Service **B1 é pago**. Revise o plano de hospedagem e os custos ao concluir a apresentação do projeto.

## Segurança

- Não versione `.env`, tokens, senhas, strings de conexão reais ou backups de banco.
- Mantenha variáveis sensíveis nas configurações de ambiente da hospedagem.
- Use HTTPS em produção.
- Utilize autenticação e autorização para acessar informações associadas a usuários e projetos.

## Projeto acadêmico

Desenvolvido no contexto da disciplina de Engenharia de Software — **Módulo 5: Agente de Curadoria Inteligente e Tendências Tecnológicas**.
