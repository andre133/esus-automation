# Como Fazer Deploy no Render.com

Configurei seu projeto para funcionar perfeitamente no Render usando **Docker**, que é necessário para o Playwright funcionar corretamente (ele precisa instalar navegadores e dependências do sistema).

## Arquivos Criados/Modificados
1.  **`Dockerfile`**: Contém as instruções para instalar o Python, as dependências do sistema para o Playwright e o próprio Playwright.
2.  **`render.yaml`**: Arquivo de configuração "Blueprint" do Render.
3.  **`requirements.txt`**: Adicionei `gunicorn` que é necessário para o servidor de produção.

## Passo a Passo para Deploy

### 1. Subir para o GitHub
Seu código precisa estar em um repositório no GitHub (ou GitLab/Bitbucket).
1.  Crie um novo repositório no GitHub.
2.  Envie seus arquivos para lá:
    ```bash
    git init
    git add .
    git commit -m "Preparando para deploy no Render"
    git branch -M main
    git remote add origin <SEU_LINK_DO_GITHUB>
    git push -u origin main
    ```

### 2. Criar no Render
1.  Acesse [dashboard.render.com](https://dashboard.render.com/).
2.  Clique em **New +** e selecione **Blueprint**.
3.  Conecte sua conta do GitHub e selecione o repositório que você acabou de criar.
4.  O Render vai detectar automaticamente o arquivo `render.yaml`.
5.  Clique em **Apply** ou **Create Web Service**.

### 3. Aguardar
O Render vai iniciar o processo de "Build". Isso pode levar alguns minutos na primeira vez pois ele vai baixar o navegador (Chromium) e instalar as dependências.

Quando terminar, você verá "Service is live" e terá uma URL (ex: `esus-automation.onrender.com`).

## Notas Importantes
- **Playwright**: O uso de Docker é essencial aqui. O ambiente padrão de Python do Render muitas vezes falha ao instalar as dependências de sistema do Playwright.
- **Porta**: O Dockerfile está configurado para usar a porta `10000`, que é o padrão do Render.
