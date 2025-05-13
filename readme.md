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
