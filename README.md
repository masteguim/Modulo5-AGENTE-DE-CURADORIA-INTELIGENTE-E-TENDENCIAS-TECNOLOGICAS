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
python -m app.cli
```

## Banco PostgreSQL no Azure

O projeto usa **Azure Database for PostgreSQL Flexible Server** e migrações
Alembic. O schema inclui usuários referenciados pelo identificador externo,
chats, conteúdos, integrações GitHub, tecnologias e recomendações. Senhas de
usuário não são armazenadas.

### Estado atual

O servidor e o banco `curadoria` já foram criados no Azure. A migração
`0001_create_curadoria_schema` foi aplicada; o comando de verificação retornou
`0001_create_curadoria_schema (head)`.

### Conferir a migração

No terminal do VS Code, na pasta do projeto, configure a URL do banco e consulte
a versão aplicada:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://USUARIO:SENHA_CODIFICADA@SERVIDOR.postgres.database.azure.com:5432/curadoria?sslmode=require"
python -m alembic current
```

O resultado esperado é:

```text
0001_create_curadoria_schema (head)
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

Para configurar uma conexão no App Service `agente-tendencias-tecnologicas`,
adicione a variável de ambiente `DATABASE_URL` com a mesma URL do banco e
reinicie o serviço.

### O que ainda falta

Ter servidor, tabelas e `DATABASE_URL` não faz a API salvar dados
automaticamente. Atualmente, `POST /consultas` não persiste conversas; falta
integrar o uso do banco ao endpoint e validar o JWT antes de associar dados a
um usuário. `project_id` é somente uma referência ao Módulo de Projetos — não
há acesso direto ao banco desse módulo.
