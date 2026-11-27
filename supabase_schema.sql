-- Run once in the SQL Editor of a new Supabase project.
-- This creates the schema from Alembic revisions 0001-0004 and records
-- 0004_remove_unused_columns as the current Alembic revision.

BEGIN;

CREATE TABLE public.usuarios (
    id_usuario SERIAL NOT NULL,
    identificador_externo VARCHAR(255) NOT NULL,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT usuarios_pkey PRIMARY KEY (id_usuario),
    CONSTRAINT uq_usuarios_identificador_externo
        UNIQUE (identificador_externo)
);

CREATE TABLE public.chats (
    id_chat SERIAL NOT NULL,
    usuario_id INTEGER NOT NULL,
    titulo VARCHAR(255) NOT NULL,
    project_id UUID,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    m7_conversation_id VARCHAR(255),
    CONSTRAINT chats_pkey PRIMARY KEY (id_chat),
    CONSTRAINT chats_usuario_id_fkey
        FOREIGN KEY (usuario_id) REFERENCES public.usuarios (id_usuario)
        ON DELETE CASCADE,
    CONSTRAINT uq_chats_m7_conversation_id UNIQUE (m7_conversation_id)
);

CREATE INDEX ix_chats_usuario_id ON public.chats (usuario_id);
CREATE INDEX ix_chats_project_id ON public.chats (project_id);

CREATE TABLE public.conteudos (
    id_conteudo SERIAL NOT NULL,
    chat_id INTEGER NOT NULL,
    pergunta TEXT NOT NULL,
    resposta TEXT,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT conteudos_pkey PRIMARY KEY (id_conteudo),
    CONSTRAINT conteudos_chat_id_fkey
        FOREIGN KEY (chat_id) REFERENCES public.chats (id_chat)
        ON DELETE CASCADE
);

CREATE INDEX ix_conteudos_chat_id ON public.conteudos (chat_id);

CREATE TABLE public.integracoes_github (
    id_github SERIAL NOT NULL,
    usuario_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    repositorio_url VARCHAR(2048),
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    project_id UUID,
    CONSTRAINT integracoes_github_pkey PRIMARY KEY (id_github),
    CONSTRAINT integracoes_github_usuario_id_fkey
        FOREIGN KEY (usuario_id) REFERENCES public.usuarios (id_usuario)
        ON DELETE CASCADE,
    CONSTRAINT integracoes_github_chat_id_fkey
        FOREIGN KEY (chat_id) REFERENCES public.chats (id_chat)
        ON DELETE CASCADE,
    CONSTRAINT uq_integracoes_github_project_url
        UNIQUE (project_id, repositorio_url)
);

CREATE INDEX ix_integracoes_github_usuario_id
    ON public.integracoes_github (usuario_id);
CREATE INDEX ix_integracoes_github_chat_id
    ON public.integracoes_github (chat_id);
CREATE INDEX ix_integracoes_github_project_id
    ON public.integracoes_github (project_id);

CREATE TABLE public.tecnologias (
    id_tecnologia SERIAL NOT NULL,
    github_id INTEGER NOT NULL,
    nome VARCHAR(255) NOT NULL,
    CONSTRAINT tecnologias_pkey PRIMARY KEY (id_tecnologia),
    CONSTRAINT tecnologias_github_id_fkey
        FOREIGN KEY (github_id) REFERENCES public.integracoes_github (id_github)
        ON DELETE CASCADE,
    CONSTRAINT uq_tecnologias_github_nome UNIQUE (github_id, nome)
);

CREATE INDEX ix_tecnologias_github_id ON public.tecnologias (github_id);

CREATE TABLE public.recomendacoes (
    id_recomendacao SERIAL NOT NULL,
    tecnologia_id INTEGER NOT NULL,
    idioma VARCHAR(45),
    fonte VARCHAR(2048),
    titulo VARCHAR(1000) NOT NULL,
    arquivo VARCHAR(2048),
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT recomendacoes_pkey PRIMARY KEY (id_recomendacao),
    CONSTRAINT recomendacoes_tecnologia_id_fkey
        FOREIGN KEY (tecnologia_id) REFERENCES public.tecnologias (id_tecnologia)
        ON DELETE CASCADE
);

CREATE INDEX ix_recomendacoes_tecnologia_id
    ON public.recomendacoes (tecnologia_id);

CREATE TABLE public.artigos (
    id SERIAL NOT NULL,
    titulo VARCHAR(1000) NOT NULL,
    link VARCHAR(2048) NOT NULL,
    fonte VARCHAR(255) NOT NULL,
    idioma VARCHAR(45) NOT NULL,
    resumo TEXT NOT NULL,
    data_publicacao VARCHAR(100),
    coletado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT artigos_pkey PRIMARY KEY (id),
    CONSTRAINT uq_artigos_link UNIQUE (link)
);

-- Protect tables exposed through the Supabase Data API. No client policies are
-- added; the backend connects directly as the database owner.
ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conteudos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integracoes_github ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tecnologias ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recomendacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.artigos ENABLE ROW LEVEL SECURITY;

CREATE TABLE public.alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INSERT INTO public.alembic_version (version_num)
VALUES ('0004_remove_unused_columns');

COMMIT;
