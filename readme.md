
# Bot de Twitter Automatizado com Selenium e IA Gemini

Este projeto é um bot para o X (antigo Twitter) que automatiza o processo de encontrar trending topics, gerar conteúdo de tweet relevante usando a API Gemini do Google e postá-lo na plataforma. Ele utiliza Selenium para automação do navegador e a biblioteca `schedule` para execuções periódicas.

## Funcionalidades Principais

*   **Busca de Trending Topics:** Acessa a seção de "Explorar > Assuntos do Momento" do X para coletar os trending topics atuais.
*   **Geração de Conteúdo com IA:** Utiliza a API Gemini do Google (modelo `gemini-1.5-flash-latest` ou configurável) para criar tweets criativos, curiosidades ou fatos interessantes sobre um trending topic selecionado.
*   **Postagem Automática:** Usa Selenium para navegar no X, abrir a caixa de diálogo de novo tweet, inserir o conteúdo gerado e publicá-lo.
*   **Agendamento:** Permite agendar a execução do bot para postar em intervalos regulares (configurável, padrão de 15 minutos).
*   **Logging Detalhado:** Registra as principais ações, sucessos e erros para facilitar o acompanhamento e a depuração.
*   **Uso de Perfil do Chrome:** Suporta o uso de um perfil existente do Google Chrome para manter a sessão do X logada, simplificando a autenticação.

## Tecnologias Utilizadas

*   **Python 3.x**
*   **Selenium:** Para automação e interação com o navegador web.
*   **WebDriver Manager:** Para gerenciamento automático do ChromeDriver.
*   **Google Gemini API:** Para geração de texto inteligente (acessada via biblioteca `requests`).
*   **Requests:** Para realizar chamadas HTTP à API Gemini.
*   **Schedule:** Para agendamento de tarefas.
*   **python-dotenv:** Para gerenciamento de variáveis de ambiente e segredos (como API Keys).
*   **Logging:** Módulo padrão do Python para registro de eventos.

## Configuração e Execução

Siga os passos abaixo para configurar e rodar o bot no seu ambiente local.

### 1. Pré-requisitos

*   Python 3.8 ou superior instalado.
*   Google Chrome instalado.
*   Uma conta no X (Twitter) ativa.
*   Uma API Key válida do Google Gemini (obtida através do [Google AI Studio](https://aistudio.google.com/)).

### 2. Clonar o Repositório (Se você estiver compartilhando)

Se você estivesse baixando este projeto de outra pessoa, você faria:
```bash
git clone https://github.com/SEU_USUARIO_GITHUB/NOME_DO_REPOSITORIO.git
cd NOME_DO_REPOSITORIO
```
(Adapte esta seção se você for o autor original e estiver instruindo outros)

### 3. Criar e Ativar Ambiente Virtual

É altamente recomendado usar um ambiente virtual para isolar as dependências do projeto. Na pasta do seu projeto:
```bash
python -m venv .venv
```

Ative o ambiente:
*   **Windows (PowerShell):**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```
    (Se encontrar erro de política de execução, tente: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` e depois ative novamente)
*   **Windows (CMD):**
    ```cmd
    .\.venv\Scripts\activate.bat
    ```
*   **Linux / macOS:**
    ```bash
    source .venv/bin/activate
    ```

### 4. Instalar Dependências

Com o ambiente virtual ativo, instale as bibliotecas necessárias:

```bash
pip install -r requirements.txt
```
(Certifique-se de ter um arquivo `requirements.txt` com as dependências como `selenium`, `webdriver-manager`, `requests`, `schedule`, `python-dotenv`)

### 5. Configurar Variáveis de Ambiente

Este projeto utiliza um arquivo `.env` para armazenar informações sensíveis como sua API Key e o caminho do perfil do Chrome.

1.  Na raiz do seu projeto, crie um arquivo chamado `.env`.
2.  Adicione o seguinte conteúdo ao arquivo `.env`, substituindo pelos seus próprios valores:

    ```env
    # .env (Exemplo - NÃO FAÇA COMMIT DESTE ARQUIVO COM SUAS CHAVES REAIS SE O REPOSITÓRIO FOR PÚBLICO SEMPRE)
    GEMINI_API_KEY="SUA_API_KEY_DO_GEMINI_AQUI"
    CHROME_PROFILE_PATH="C:\Caminho\Para\Seu\Perfil\Do\Chrome\User Data\Profile Selenium"
    # Opcional: SCHEDULE_INTERVAL_MINUTES="30"
    ```
    *   **GEMINI_API_KEY:** Sua chave de API do Google Gemini. **Mantenha esta chave segura!**
    *   **CHROME_PROFILE_PATH:** O caminho para o diretório do seu perfil do Google Chrome.
    *   **Importante:** O arquivo `.env` DEVE estar listado no seu `.gitignore`.

### 6. (Opcional) Ajustar Configurações no Script

Você pode ajustar outras configurações diretamente no script Python (ex: `meu_bot.py`), como:
*   `GEMINI_MODEL_ID`
*   `SCHEDULE_INTERVAL_MINUTES` (se não usar a variável de ambiente).
*   Prompts para a IA Gemini.

### 7. Executar o Bot

Com o ambiente virtual ativo e as configurações prontas:

*   **Para uma única execução de teste (como o script está configurado por padrão):**
    ```bash
    python nome_do_seu_script.py
    ```

*   **Para rodar continuamente com agendamento:**
    Edite o final do script `nome_do_seu_script.py` para habilitar o loop de agendamento contínuo (descomente o bloco `if __name__ == "__main__":` apropriado).
    ```bash
    python nome_do_seu_script.py
    ```
    Para parar o bot, pressione `Ctrl+C` no terminal.

## Estrutura do Projeto (Simplificada)

```
.
├── .venv/                   # Ambiente virtual (ignorado pelo Git)
├── screenshots_twitter_bot/ # Pasta para screenshots de debug (pode ser ignorada pelo Git)
├── .env                     # Arquivo com suas API keys e caminhos (DEVE ser ignorado pelo Git)
├── .gitignore               # Especifica arquivos e pastas a serem ignorados pelo Git
├── requirements.txt         # Lista de dependências Python
├── bot_x.py    # O script principal do bot
└── README.md                # Este arquivo
```

## Possíveis Melhorias Futuras

*   Refatoração do código para utilizar uma estrutura baseada em classes para melhor organização.
*   Aprimoramento da lógica de seleção de trends e filtragem.
*   Melhoria contínua dos prompts para a API Gemini para gerar conteúdo ainda mais relevante e engajador.
*   Implementação de tratamento de erro mais granular para diferentes cenários de falha.
*   Adição de funcionalidade para incluir imagens ou GIFs nos tweets.
*   Opção para configurar diferentes "personalidades" ou tons para os tweets gerados.
*   Deploy do bot em um servidor ou plataforma cloud para operação 24/7.

## Licença

Este projeto é distribuído sob a licença MIT. 

---

*Este é um projeto de aprendizado e demonstração. Use com responsabilidade e esteja ciente das políticas de automação da plataforma X (Twitter) e dos termos de uso das APIs utilizadas.*
```

---




