import logging
import random
import time
import json
import requests
import os

from dotenv import load_dotenv
load_dotenv() # Carrega variáveis de ambiente do arquivo .env, se existir

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
# from selenium.webdriver.common.keys import Keys # Keys não está sendo usado, pode ser removido

import schedule

# --- CONFIGURAÇÕES GLOBAIS ---
# Estas são as configurações principais que o bot utiliza.
# Recomenda-se usar variáveis de ambiente (via arquivo .env) para informações sensíveis.

# Chave da API para o serviço Google Gemini. Deve ser configurada no arquivo .env.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Identificador do modelo Gemini a ser utilizado para geração de texto.
GEMINI_MODEL_ID = "gemini-1.5-flash-latest" 

# URL base para a API do Google Gemini (usando Google AI Studio).
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_ID}:generateContent?key={GEMINI_API_KEY}"
# Para Vertex AI, a URL e autenticação seriam diferentes e geralmente não envolvem passar a API key diretamente na URL.

# Configurações relacionadas ao Selenium e ao X (Twitter)
PROFILE_PATH = os.getenv("CHROME_PROFILE_PATH")  # Caminho para um perfil do Chrome existente (opcional, para manter login).
TWITTER_BASE_URL = "https://x.com"  # URL base da plataforma X.
TWITTER_TRENDS_URL = f"{TWITTER_BASE_URL}/explore/tabs/trending"  # URL da página de trending topics.
TWITTER_HOME_URL_FOR_TWEET_BUTTON = f"{TWITTER_BASE_URL}/home" # URL da home, usada para acesso mais estável ao botão de postar.

# Outras Configurações do Bot
MAX_TWEET_CHARACTERS = 260  # Limite de caracteres para o tweet gerado (considerando uma margem).
SCHEDULE_INTERVAL_MINUTES = 90  # Intervalo em minutos para a execução automática da tarefa de postagem.
SCREENSHOT_DIR = "BOT_X/screenshots_twitter_bot" # Diretório para salvar screenshots em caso de erro.

# Configuração do sistema de Logging para registrar eventos e erros.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Cria o diretório de screenshots se ele não existir.
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

# Verificações iniciais de configuração crucial.
if not GEMINI_API_KEY:
    logging.critical("CRÍTICO: GEMINI_API_KEY não encontrada no arquivo .env! O bot não pode funcionar.")
    exit("Saindo: GEMINI_API_KEY não configurada.") # Encerra o script se a chave não estiver presente.
if not PROFILE_PATH:
    # Aviso se o perfil do Chrome não for especificado; o bot usará um perfil temporário.
    logging.warning("CHROME_PROFILE_PATH não encontrado no .env. O WebDriver usará um perfil temporário/padrão.")


def init_driver(profile_path_arg):
    """
    Inicializa e retorna uma instância do WebDriver do Chrome.

    Configura as opções do Chrome, incluindo o uso de um perfil de usuário (se fornecido),
    idioma, maximização da janela e outras otimizações para automação.

    Args:
        profile_path_arg (str): O caminho para o diretório de perfil do usuário do Chrome.
                                Pode ser None para usar um perfil temporário/padrão.
    Returns:
        webdriver.Chrome: A instância do driver do Chrome configurada.
    Raises:
        Exception: Se houver um erro durante a inicialização do WebDriver.
    """
    logging.info("Configurando opções do WebDriver do Chrome...")
    options = Options()
    if profile_path_arg: # Usa o perfil do Chrome se um caminho for fornecido.
        logging.info(f"Utilizando perfil do Chrome localizado em: {profile_path_arg}")
        options.add_argument(f"user-data-dir={profile_path_arg}")
    else:
        logging.info("Nenhum perfil do Chrome especificado. Usando perfil padrão/temporário.")
    
    # Opções diversas para o comportamento do navegador.
    options.add_argument("--lang=pt-BR") # Define o idioma do navegador.
    options.add_argument("--start-maximized") # Inicia o navegador maximizado.
    options.add_argument("--disable-notifications") # Desabilita notificações do Chrome.
    options.add_argument("--disable-gpu") # Recomendado para ambientes headless ou para evitar problemas de renderização.
    options.add_argument("--no-sandbox") # Necessário em alguns ambientes Linux/Docker.
    options.add_argument("--disable-dev-shm-usage") # Resolve problemas de recursos em alguns ambientes Linux.
    # options.add_argument("--headless") # Descomente para rodar sem interface gráfica (após testes).

    logging.info("Instalando/Obtendo ChromeDriver via webdriver_manager...")
    try:
        # Utiliza webdriver_manager para baixar e configurar o ChromeDriver automaticamente.
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logging.info("WebDriver do Chrome inicializado com sucesso.")
        return driver
    except Exception as e:
        logging.error(f"Falha ao inicializar o WebDriver do Chrome: {e}", exc_info=True)
        raise # Re-levanta a exceção para que a falha seja tratada no nível superior.

def get_tweet_content_from_gemini(trend_topic):
    """
    Gera o conteúdo de um tweet sobre um tópico específico usando a API Gemini.

    Args:
        trend_topic (str): O tópico (trending topic) para o qual o tweet será gerado.

    Returns:
        str or None: O texto do tweet gerado, ou None se ocorrer um erro.
    """
    logging.info(f"Solicitando à API Gemini a geração de um tweet para o tópico: '{trend_topic}'")
    headers = {"Content-Type": "application/json"} # Cabeçalho padrão para requisições JSON.
    
    # Prompt detalhado para guiar a IA Gemini na criação do tweet.
    prompt = (
        f"O termo '{trend_topic}' está atualmente em alta no X (antigo Twitter). "
        f"Crie um tweet curto e engajador (máximo de {MAX_TWEET_CHARACTERS - 45} caracteres) "
        f"que compartilhe uma curiosidade interessante ou um fato pouco conhecido sobre '{trend_topic}', "
        f"considerando seu contexto como um assunto popular online. "
        f"Se o tópico envolver uma inovação, destaque brevemente seu potencial impacto. "
        f"Inclua 1 hashtag somente, que seja relevante. " # Pede uma única hashtag relevante.
        f"O tom deve ser informativo e curioso. "
        f"Não use datas ou anos específicos. Não use saudações. Não inclua links. Não use colchetes [] na resposta final."
        f"Responda APENAS com o texto do tweet." # Garante que a resposta seja apenas o tweet.
    )
    
    # Payload da requisição para a API Gemini.
    data_payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": { # Configurações para controlar a geração de texto.
            "temperature": 0.50, # Controla a "criatividade" (valores menores são mais determinísticos).
            "maxOutputTokens": 150, # Limite máximo de tokens na resposta.
            "topP": 0.95, # Parâmetro de amostragem (nucleus sampling).
            "topK": 40    # Parâmetro de amostragem (top-k sampling).
        },
        # Configurações de segurança para filtrar conteúdo indesejado (comentadas, mas recomendadas).
        # "safetySettings": [
        #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}, ...
        # ]
    }

    try:
        logging.debug(f"Enviando requisição para API Gemini. URL: {GEMINI_API_URL}")
        logging.debug(f"Payload da requisição Gemini: {json.dumps(data_payload, indent=2)}")
        response = requests.post(GEMINI_API_URL, headers=headers, json=data_payload, timeout=45)
        
        logging.debug(f"API Gemini - Status da Resposta: {response.status_code}")
        logging.debug(f"API Gemini - Corpo da Resposta (parcial): {response.text[:500]}")

        response.raise_for_status() # Levanta um erro HTTP para status ruins (4xx ou 5xx).
        
        data = response.json() # Converte a resposta JSON em um dicionário Python.
        
        # Extrai o texto do tweet da estrutura de resposta da API Gemini.
        if "candidates" in data and data["candidates"]:
            candidate = data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"] and candidate["content"]["parts"]:
                tweet_text = candidate["content"]["parts"][0]["text"].strip()
            else:
                logging.error(f"API Gemini: Estrutura de resposta inesperada (sem 'content' ou 'parts'). Candidato: {candidate}")
                return None
        else:
            logging.error(f"API Gemini: Nenhum candidato retornado ou estrutura de resposta inesperada. Resposta: {data}")
            if "promptFeedback" in data and "blockReason" in data["promptFeedback"]: # Verifica se o prompt foi bloqueado.
                logging.error(f"API Gemini: Prompt bloqueado. Razão: {data['promptFeedback']['blockReason']}")
            return None
            
        # Trunca o tweet se exceder o limite máximo de caracteres.
        if len(tweet_text) > MAX_TWEET_CHARACTERS:
            tweet_text = tweet_text[:MAX_TWEET_CHARACTERS-3] + "..."
            logging.warning(f"Tweet gerado foi truncado para {MAX_TWEET_CHARACTERS} caracteres.")
            
        logging.info(f"Tweet gerado pela API Gemini: '{tweet_text}'")
        return tweet_text
    except requests.exceptions.RequestException as e: # Erros de rede ou HTTP.
        logging.error(f"Erro de requisição ao contatar a API Gemini: {e}")
    except (KeyError, IndexError, TypeError) as e: # Erros ao processar a estrutura do JSON.
        logging.error(f"Erro ao processar a resposta da API Gemini: {e} - Resposta: {data if 'data' in locals() else 'N/A'}")
    except json.JSONDecodeError as e: # Erro se a resposta não for um JSON válido.
        logging.error(f"Erro ao decodificar JSON da API Gemini: {e} - Resposta (texto): {response.text if 'response' in locals() else 'N/A'}")
    return None # Retorna None em caso de qualquer erro.


def select_trends_from_twitter(driver):
    """
    Navega até a página de trending topics do X e extrai uma lista de trends.

    Args:
        driver (webdriver.Chrome): A instância do WebDriver do Chrome.

    Returns:
        list: Uma lista de strings contendo os nomes das trends encontradas e filtradas.
              Retorna uma lista vazia se ocorrer um erro ou nenhuma trend for encontrada.
    """
    logging.info(f"Acessando a página de trending topics: {TWITTER_TRENDS_URL}")
    driver.get(TWITTER_TRENDS_URL)
    wait = WebDriverWait(driver, 20) # Define um tempo máximo de espera para os elementos.

    try:
        # XPath para localizar o contêiner principal que agrupa os trending topics.
        # Inclui variações de 'aria-label' para diferentes idiomas ou versões da UI.
        trends_container_xpath = (
            '//div[@aria-label="Timeline: Explore" or '
            '@aria-label="Linha do Tempo: Explorar" or '
            '@aria-label="Timeline: Trending now" or '
            '@aria-label="Timeline: Assuntos do momento"]'
        )
        # Espera até que o contêiner de trends esteja visível na página.
        trends_container = wait.until(
            EC.visibility_of_element_located((By.XPATH, trends_container_xpath))
        )
        logging.info("Contêiner de trending topics encontrado.")

        # XPath para extrair o texto principal (nome) de cada item de trend.
        # Este XPath tenta ser específico para o elemento que contém o nome da trend.
        trend_elements_xpath = './/div[@data-testid="trend"]/div/div[2]/span'
        # Alternativa (comentada): um XPath mais genérico que pode pegar mais ruído,
        # mas pode ser útil se a estrutura da página mudar significativamente.
        # trend_elements_xpath_alternative = './/div[@data-testid="trend"]//span'

        # Espera que pelo menos alguns elementos de trend individuais estejam presentes no DOM.
        wait.until(EC.presence_of_all_elements_located((By.XPATH, './/div[@data-testid="trend"]')))
        
        # Encontra todos os elementos candidatos a serem nomes de trends.
        candidate_elements = trends_container.find_elements(By.XPATH, trend_elements_xpath)
        
        trends_texts = []
        for elem in candidate_elements:
            text = elem.text.strip() # Pega o texto do elemento e remove espaços extras.
            # Aplica filtros para remover textos que provavelmente não são trends reais.
            if text and \
               not text.isdigit() and \
               "posts" not in text.lower() and \
               "tweets" not in text.lower() and \
               "·" not in text and \
               2 < len(text) < 50: # Filtra por tamanho para evitar textos muito curtos ou longos.
                trends_texts.append(text)
        
        # Remove trends duplicadas mantendo a ordem de aparição.
        unique_trends = list(dict.fromkeys(trends_texts)) 

        logging.info(f"Trends encontradas e pré-filtradas ({len(unique_trends)}): {unique_trends[:10]}") # Loga as 10 primeiras.
        return unique_trends

    except TimeoutException:
        logging.error("Timeout ao tentar encontrar os trending topics. A página pode não ter carregado ou os seletores mudaram.")
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_selecting_trends_timeout.png"))
    except Exception as e: # Captura outras exceções durante a seleção de trends.
        logging.error(f"Erro inesperado ao selecionar trends: {e}", exc_info=True)
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_selecting_trends_generic.png"))
    return [] # Retorna lista vazia em caso de erro.


def post_tweet_on_twitter(driver, tweet_content):
    """
    Posta um tweet na plataforma X usando a instância do WebDriver.

    Args:
        driver (webdriver.Chrome): A instância do WebDriver.
        tweet_content (str): O texto do tweet a ser postado.

    Returns:
        bool: True se o tweet foi postado com sucesso, False caso contrário.
    """
    logging.info("Iniciando processo de postagem do tweet.")
    logging.info(f"Navegando para a página inicial do X: {TWITTER_HOME_URL_FOR_TWEET_BUTTON}")
    driver.get(TWITTER_HOME_URL_FOR_TWEET_BUTTON) # Acessa a home para ter o botão de postar de forma mais consistente.
    wait = WebDriverWait(driver, 30) # Tempo de espera aumentado para a página inicial.

    try:
        # XPath para o botão principal de "Postar" ou "Novo Tweet" na interface.
        post_button_xpath = "//a[@data-testid='SideNav_NewTweet_Button']"
        logging.info(f"Procurando o botão principal de postar com XPath: {post_button_xpath}")
        post_button = wait.until(EC.element_to_be_clickable((By.XPATH, post_button_xpath)))
        
        # Garante que o botão esteja visível na tela antes de clicar.
        driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", post_button)
        time.sleep(0.5) # Pequena pausa após o scroll.
        post_button.click()
        logging.info("Botão principal de 'Postar' clicado.")
        time.sleep(1.5) # Pausa para a caixa de diálogo de composição do tweet abrir.

        # XPath para a área de texto onde o tweet será digitado.
        tweet_textarea_xpath = "//div[@data-testid='tweetTextarea_0']"
        logging.info(f"Procurando a caixa de texto do tweet com XPath: {tweet_textarea_xpath}")
        tweet_textarea = wait.until(EC.visibility_of_element_located((By.XPATH, tweet_textarea_xpath)))
        
        logging.info(f"Inserindo texto na caixa de tweet (primeiros 50 chars): '{tweet_content[:50]}...'")
        tweet_textarea.send_keys(tweet_content) # Digita o conteúdo do tweet.
        time.sleep(1) # Pausa após digitar.

        # XPath para o botão final de "Postar" dentro da caixa de diálogo de composição.
        submit_tweet_button_xpath = "//button[@data-testid='tweetButton']"
        logging.info(f"Procurando o botão de submissão do tweet com XPath: {submit_tweet_button_xpath}")
        submit_tweet_button = wait.until(EC.element_to_be_clickable((By.XPATH, submit_tweet_button_xpath)))
        
        driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", submit_tweet_button)
        time.sleep(0.5)
        
        # Tenta o clique normal primeiro; se interceptado, tenta via JavaScript.
        try:
            submit_tweet_button.click()
        except ElementClickInterceptedException:
            logging.warning("Clique normal no botão de submeter tweet foi interceptado. Tentando clique via JavaScript.")
            driver.execute_script("arguments[0].click();", submit_tweet_button)

        logging.info("Botão de submissão do tweet clicado.")
        # Espera a confirmação da postagem, verificando se o botão de submissão desapareceu.
        wait.until(EC.invisibility_of_element_located((By.XPATH, submit_tweet_button_xpath)))
        logging.info("Tweet postado com sucesso! Caixa de diálogo de composição fechada.")
        return True

    except TimeoutException as e:
        logging.error(f"Timeout durante o processo de postagem do tweet: {e}")
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_posting_tweet_timeout.png"))
    except ElementClickInterceptedException as e: # Erro específico se o clique for bloqueado.
        logging.error(f"ElementClickInterceptedException ao tentar postar o tweet: {e}")
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_posting_tweet_intercepted.png"))
    except Exception as e: # Captura outras exceções.
        logging.error(f"Erro inesperado ao tentar postar o tweet: {e}", exc_info=True)
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_posting_tweet_generic.png"))
    return False


def twitter_bot_task():
    """
    Executa um ciclo completo da tarefa do bot:
    1. Inicializa o WebDriver.
    2. Seleciona um trending topic.
    3. Gera conteúdo de tweet para o topic.
    4. Posta o tweet.
    5. Fecha o WebDriver.
    """
    logging.info("--- Iniciando ciclo da tarefa do bot do Twitter ---")
    driver = None # Inicializa driver como None para o bloco finally.
    try:
        # Usa a variável global PROFILE_PATH definida no topo do script.
        driver = init_driver(PROFILE_PATH) 
        
        trends = select_trends_from_twitter(driver) # Busca os trending topics.

        if trends: # Se alguma trend for encontrada.
            chosen_trend = random.choice(trends) # Escolhe uma aleatoriamente.
            logging.info(f"Trend selecionada para este ciclo: '{chosen_trend}'")
            
            tweet_text = get_tweet_content_from_gemini(chosen_trend) # Gera o tweet.
            
            if tweet_text: # Se o conteúdo do tweet for gerado com sucesso.
                if post_tweet_on_twitter(driver, tweet_text): # Tenta postar.
                    logging.info(f"Tarefa concluída com sucesso! Tweet postado para a trend: '{chosen_trend}'")
                else:
                    logging.warning("Falha ao tentar postar o tweet neste ciclo.")
            else:
                logging.warning("Não foi possível gerar conteúdo para o tweet com a API Gemini.")
        else:
            logging.warning("Nenhuma trend foi encontrada ou selecionada neste ciclo.")

    except Exception as e: # Captura exceções gerais durante a execução da tarefa.
        logging.error(f"Erro geral durante a execução da tarefa do bot: {e}", exc_info=True)
        if driver: # Tenta salvar um screenshot se o driver ainda existir.
            try:
                driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_twitter_bot_task.png"))
            except Exception as e_ss: 
                logging.error(f"Falha ao salvar screenshot do erro da tarefa: {e_ss}")
    finally:
        # Garante que o WebDriver seja fechado, mesmo se ocorrerem erros.
        if driver:
            logging.info("Fechando o WebDriver ao final da tarefa.")
            driver.quit()
        logging.info("--- Ciclo da tarefa do bot do Twitter finalizado ---")


# --- AGENDAMENTO DA TAREFA ---
# Configura a tarefa `twitter_bot_task` para ser executada no intervalo definido.
logging.info(f"Agendando a tarefa do bot para executar a cada {SCHEDULE_INTERVAL_MINUTES} minutos.")
schedule.every(SCHEDULE_INTERVAL_MINUTES).minutes.do(twitter_bot_task)

# Bloco principal que mantém o script rodando para o agendador funcionar.
if __name__ == "__main__":
    logging.info("Iniciando loop de agendamento do bot. Pressione Ctrl+C para sair.")
    
    # Executa todas as tarefas agendadas uma vez imediatamente ao iniciar.
    # Útil para verificar se a tarefa funciona sem esperar o primeiro intervalo.
    try:
        logging.info("Executando a tarefa uma vez imediatamente...")
        twitter_bot_task() # Executa a tarefa diretamente uma vez.
        # Ou: schedule.run_all(delay_seconds=1) # Se houvesse múltiplas tarefas agendadas.
    except Exception as e:
        logging.error(f"Erro durante a primeira execução imediata da tarefa: {e}", exc_info=True)

    logging.info(f"Próxima execução agendada: {schedule.next_run() if schedule.jobs else 'Nenhuma tarefa agendada.'}")
    
    # Loop infinito que verifica e executa tarefas pendentes.
    while True:
        try:
            schedule.run_pending() # Verifica e executa tarefas agendadas.
            time.sleep(1)          # Pausa por 1 segundo para não sobrecarregar a CPU.
        except KeyboardInterrupt:  # Permite encerrar o bot com Ctrl+C.
            logging.info("Loop de agendamento interrompido pelo usuário (Ctrl+C). Encerrando...")
            break
        except Exception as e:     # Captura outros erros inesperados no loop de agendamento.
            logging.error(f"Erro crítico no loop de agendamento principal: {e}", exc_info=True)
            logging.info("Aguardando 60 segundos antes de tentar continuar o loop de agendamento...")
            time.sleep(60)         # Pausa antes de tentar continuar em caso de erro grave no loop.