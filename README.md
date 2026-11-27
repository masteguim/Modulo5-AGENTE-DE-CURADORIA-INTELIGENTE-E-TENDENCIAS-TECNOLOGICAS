# Curadoria Inteligente — Módulo 5

API do agente de curadoria de tendências tecnológicas.

## Executar localmente

Instale as dependências:

```powershell
python -m pip install -r requirements.txt
```

Configure a conexão local uma vez:

```powershell
Copy-Item .env.example .env
```

Abra `.env`, substitua o valor de `DATABASE_URL` pela URI **Session Pooler**
do Supabase e salve. O arquivo `.env` é local e ignorado pelo Git; não o
compartilhe nem faça commit.

Como o schema já foi criado pelo SQL Editor, atualize-o com:

```powershell
python -m alembic upgrade head
python -m alembic current
```

O resultado esperado é `0004_remove_unused_columns (head)`.

Para iniciar a API:

```powershell
python -m uvicorn app.main:app --reload
```

O backend e o Alembic leem essa configuração do `.env` automaticamente.

A documentação interativa fica em <http://127.0.0.1:8000/docs>.

Para usar o cliente de terminal do MVP:

```powershell
$env:M1_ACCESS_TOKEN = "<access_token individual do Módulo 1>"
python -m app.cli
Remove-Item Env:M1_ACCESS_TOKEN
```

## Banco PostgreSQL no Supabase

O projeto usa PostgreSQL padrão com SQLAlchemy, `psycopg` e migrações Alembic;
não depende de recursos exclusivos do Azure nem do SDK do Supabase. O schema
inclui usuários referenciados pelo identificador externo, chats, conteúdos,
integrações GitHub, tecnologias e recomendações. Senhas de usuário não são
armazenadas.

No Supabase, crie um projeto PostgreSQL e copie a URI do **Session Pooler** em
**Connect**. O Session Pooler é a opção recomendada para a API hospedada no
Azure App Service. A aplicação exige o driver `postgresql+psycopg`; se a URI
copiada começar com `postgresql://`, troque o prefixo para
`postgresql+psycopg://`. Mantenha `sslmode=require` e codifique caracteres
especiais da senha para URL.

Para criar o schema pelo SQL Editor do Supabase, execute uma única vez o arquivo
[supabase_schema.sql](./supabase_schema.sql) em um projeto vazio. O script
também registra a revisão Alembic `0004_remove_unused_columns` e ativa RLS
nas tabelas da aplicação; não o execute novamente em um banco já migrado.
Se você já executou uma versão anterior do script, aplique as migrações para
atualizar o schema, em vez de executar o script novamente.

### Status: feito no código

- Conexão PostgreSQL via `DATABASE_URL` e migrações Alembic.
- Persistência de artigos, consultas e histórico de conversas por usuário.
- Autenticação com JWT RS256 do Módulo 1, validação por JWKS e confirmação
  da sessão em `/auth/me`.
- Proxy de login, MFA, renovação de token e logout do Módulo 1, para o
  navegador não depender do CORS da API de identidade.
- Verificação de acesso a projetos pelo endpoint HTTP do Módulo 1; não há
  acesso ao banco de outro módulo.
- Chamada autenticada ao `/api/chat` do Módulo 7 e persistência do identificador
  da conversa externa.
- Registro de repositórios GitHub, stack e recomendações associadas ao projeto.
- O CLI usa `M1_ACCESS_TOKEN`; as instruções das rotas estão neste README.
- Validação local após a integração: 30 testes passaram e Ruff passou.

### Pendente antes de considerar a integração operacional

- Como o SQL anterior já foi executado, aplicar a nova migração ao Supabase
  com `python -m alembic upgrade head`. Ela remove os quatro campos sem uso e
  o índice desnecessário. Depois, confirme que
  `python -m alembic current` retorna `0004_remove_unused_columns (head)`.
- Configurar a `DATABASE_URL` do Supabase no ambiente da API. O workflow atual
  do GitHub Actions não injeta essa variável; mantenha-a nas configurações de
  ambiente do App Service, não no repositório.
- **Bloqueio separado:** na última verificação, o App Service da API estava
  com status `Cota excedida` e o Azure respondia `403 - This web app is
  stopped`. Migrar o banco para Supabase não corrige a cota nem inicia a API;
  o plano de hospedagem precisa voltar a aceitar requisições.
- O frontend foi integrado localmente no repositório
  `Modulo5-CURADORIA-INTELIGENTE-E-TENDENCIAS-TECNOLOGICAS`, mas ainda precisa
  ser publicado. O login/MFA, Bearer, renovação e histórico só funcionarão em
  produção depois que API e frontend atualizados estiverem publicados.
- Fazer um teste integrado real com PostgreSQL no Supabase, Módulo 1 e Módulo
  7. Os testes locais não acessaram esses serviços.
- O schema foi simplificado removendo nome/e-mail local do usuário,
  identificador numérico do repositório, tipo da tecnologia e o índice de data
  de publicação sem uso nas consultas atuais. A identidade continua
  referenciada pelo subject externo; o e-mail do perfil vem do Módulo 1.

As recomendações são geradas a partir dos artigos já armazenados; execute o
coletor para alimentar esses artigos antes de cadastrar um repositório.

### Conferir a migração

Com o `.env` configurado, rode `python -m alembic current`. O resultado
esperado é `0004_remove_unused_columns (head)`. Se ainda estiver em uma
revisão anterior, rode `python -m alembic upgrade head`.

Não compartilhe nem salve a senha no repositório. Se ela tiver caracteres
especiais, use a versão codificada para URL.

### Configuração da conexão da API

Configure a mesma URI do Supabase como `DATABASE_URL` nas configurações de
ambiente do serviço que hospeda a API. No App Service, use
**Variáveis de ambiente → Configurações de aplicativo**. Não inclua a senha no
GitHub, no `.env.example` ou em commits. Se houver restrições de rede no projeto
Supabase, permita apenas os endereços de saída necessários da API e o endereço
do computador usado para executar migrações.

### Integração por usuário e projetos

As operações que salvam dados de uma pessoa exigem o token de acesso individual
do Módulo 1 no cabeçalho `Authorization: Bearer <access_token>`. O backend
valida RS256, issuer, audience e JWKS e confirma a sessão em `/auth/me`. Ele não
armazena senha nem aceita token compartilhado. O frontend usa o proxy abaixo
para o login e mantém os tokens apenas em `sessionStorage`.

O backend usa estes serviços por padrão:

- Identidade: `https://mod1-auth.whitemeadow-deba1090.brazilsouth.azurecontainerapps.io`
- Assistente: `https://mackai-conversas.calmfield-d7c6c49f.brazilsouth.azurecontainerapps.io`

Opcionalmente, configure `M1_AUTH_URL`, `M1_JWT_ISSUER`,
`M1_JWT_AUDIENCE`, `M1_JWKS_URL` e `M7_BASE_URL` no ambiente da API.

Rotas integradas:

| Método e rota | Uso |
| --- | --- |
| `POST /auth/login` | Encaminha e-mail e senha como formulário para `/auth/token` do Módulo 1 |
| `POST /auth/mfa/verify` | Encaminha o desafio e um código MFA ou de recuperação |
| `POST /auth/refresh` | Renova o token por meio do Módulo 1 |
| `POST /auth/logout` | Encerra a sessão no Módulo 1 |
| `GET /auth/session` | Confirma a sessão ativa e retorna o perfil básico autenticado |
| `POST /consultas` | Busca artigos e salva pergunta/resposta no histórico da pessoa |
| `POST /assistente` | Envia a pergunta ao `POST /api/chat` do Módulo 7 e salva a conversa |
| `GET /conversas` e `GET /conversas/{chat_id}` | Lista e consulta apenas o histórico da pessoa autenticada |
| `POST /projetos/{project_id}/repositorios` | Verifica acesso ao projeto no Módulo 1, detecta a stack pública no GitHub e salva o vínculo |
| `GET /projetos/{project_id}/repositorios` | Lista os repositórios e tecnologias salvos para o projeto |
| `GET /projetos/{project_id}/recomendacoes` | Lista recomendações persistidas por tecnologia para o projeto |

`project_id` é o UUID da API de Projetos do Módulo 1. O Módulo 5 não acessa o
banco de outro módulo: verifica acesso por HTTP. A rota de repositórios associa
ao projeto os artigos de recomendação disponíveis no banco; execute o coletor
para alimentar os artigos primeiro. Em `/assistente`, envie `project_id` para
uma conversa de projeto; para continuar uma conversa, envie o `chat_id` local
retornado pelo Módulo 5. `GET /conversas` sem `project_id` lista conversas
gerais; para o histórico de um projeto, informe seu UUID na query string.
Repositórios e recomendações ficam associados ao projeto e são visíveis a
qualquer pessoa que tenha acesso atual a ele; o histórico de conversas continua
restrito à pessoa que o criou.

Exemplo local para perguntar ao Módulo 7:

```powershell
$headers = @{ Authorization = "Bearer $env:M1_ACCESS_TOKEN" }
$body = @{
    pergunta = "Resuma a stack deste projeto"
    project_id = "<UUID do projeto>"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/assistente" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body
```

Ordem sugerida para continuar:

1. Copie a URI Session Pooler do projeto Supabase e configure `DATABASE_URL`
   localmente.
2. Rode `python -m alembic upgrade head` e depois
   `python -m alembic current`; o esperado é
   `0004_remove_unused_columns (head)`.
3. Configure `DATABASE_URL` no ambiente da API. Se continuar no Azure, resolva
   antes o status `Cota excedida` do App Service.
4. Publique a API e o frontend, com `VITE_API_URL` apontando para a raiz da API
   (por exemplo, `https://<host-da-api>`).
5. Teste login/MFA, `/auth/session`, consulta, histórico e integração GitHub
   com uma conta individual e um projeto ao qual ela tenha acesso.
6. Revise as restrições de rede do projeto Supabase para permitir apenas as
   conexões necessárias.

Não compartilhe tokens ou senhas no chat nem os salve no repositório.
