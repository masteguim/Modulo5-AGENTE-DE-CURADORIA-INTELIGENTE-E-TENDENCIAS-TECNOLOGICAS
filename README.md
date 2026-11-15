# Curadoria Inteligente — Módulo 5

API do agente de curadoria de tendências tecnológicas.

## Executar localmente

Instale as dependências:

```powershell
python -m pip install -r requirements.txt
```

Para iniciar a API:

```powershell
python -m uvicorn app.main:app --reload
```

A documentação interativa fica em <http://127.0.0.1:8000/docs>.

Para usar o cliente de terminal do MVP:

```powershell
$env:M1_ACCESS_TOKEN = "<access_token individual do Módulo 1>"
python -m app.cli
Remove-Item Env:M1_ACCESS_TOKEN
```

## Banco PostgreSQL no Azure

O projeto usa **Azure Database for PostgreSQL Flexible Server** e migrações
Alembic. O schema inclui usuários referenciados pelo identificador externo,
chats, conteúdos, integrações GitHub, tecnologias e recomendações. Senhas de
usuário não são armazenadas.

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

- O servidor e o banco `curadoria` já foram criados no Azure. A última
  confirmação registrada indicava a migração `0001_create_curadoria_schema`;
  não foi confirmado que `0002` e `0003` tenham sido aplicadas.
- Publicar a versão atualizada da API no Azure, incluindo o proxy de
  autenticação, e confirmar que o App Service tem `DATABASE_URL` configurada.
- O frontend foi integrado localmente no repositório
  `Modulo5-CURADORIA-INTELIGENTE-E-TENDENCIAS-TECNOLOGICAS`, mas ainda precisa
  ser publicado. O login/MFA, Bearer, renovação e histórico só funcionarão em
  produção depois que API e frontend atualizados estiverem publicados.
- Fazer um teste integrado real com PostgreSQL no Azure, Módulo 1 e Módulo 7.
  Os testes locais não acessaram esses serviços.
- Restringir o firewall do PostgreSQL. A regra ampla foi mantida por enquanto
  a pedido, mas deixa o servidor acessível de qualquer IP IPv4 e não é adequada
  para produção.

As recomendações são geradas a partir dos artigos já armazenados; execute o
coletor para alimentar esses artigos antes de cadastrar um repositório.

### Conferir a migração

No terminal do VS Code, na pasta do projeto, configure a URL do banco e consulte
a versão aplicada:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://USUARIO:SENHA_CODIFICADA@SERVIDOR.postgres.database.azure.com:5432/curadoria?sslmode=require"
python -m alembic current
```

O resultado esperado após atualizar as tabelas é:

```text
0003_integrate_user_workflows (head)
```

Se ainda precisar criar ou atualizar as tabelas, execute:

```powershell
python -m alembic upgrade head
```

Ao terminar, remova a variável do terminal:

```powershell
Remove-Item Env:DATABASE_URL
```

Não compartilhe nem salve a senha no repositório. Se ela tiver caracteres
especiais, use a versão codificada para URL.

### Rede e configuração da API

O firewall do PostgreSQL deve permitir somente os IPs necessários: o IP do
computador enquanto executa a migração e os IPs de saída do App Service da API.
**Não use uma regra que libere todos os IPs da internet.**

Para configurar a conexão no App Service `agente-tendencias-tecnologicas`,
adicione `DATABASE_URL` nas configurações de ambiente e reinicie o serviço.

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

1. Configure `DATABASE_URL` localmente e rode `python -m alembic upgrade head`.
2. Rode `python -m alembic current`; o esperado é
   `0003_integrate_user_workflows (head)`.
3. Publique a API e configure `DATABASE_URL` no App Service.
4. Publique o frontend com `VITE_API_URL` apontando para a raiz da API
   (por exemplo, `https://<host-da-api>`).
5. Teste login/MFA, `/auth/session`, consulta, histórico e integração GitHub
   com uma conta individual e um projeto ao qual ela tenha acesso.
6. Restrinja o firewall do PostgreSQL aos IPs necessários.

Não compartilhe tokens ou senhas no chat nem os salve no repositório.
