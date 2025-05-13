import logging
import random
import time
import json
import requests
import os

from dotenv import load_dotenv
load_dotenv()  # Carrega variáveis de ambiente do arquivo .env, se existir

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.keys import Keys

import schedule

# --- CONFIGURAÇÕES GLOBAIS ---
# Chave da API Gemini (Mantenha segura! Idealmente, use variáveis de ambiente)
# Substitua pelo seu PROJECT_ID se estiver usando a API do Vertex AI
# ou deixe apenas a API_KEY se estiver usando a API do Google AI Studio diretamente
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # <--- SUBSTITUA PELA SUA CHAVE REAL
# Escolha o modelo Gemini apropriado (ex: gemini-pro, gemini-1.0-pro, gemini-1.5-flash-latest etc.)
GEMINI_MODEL_ID = "gemini-1.5-flash-latest" # Ou o modelo que você tem acesso

# Define o endpoint baseado se é Google AI Studio (genai.googleapis.com) ou Vertex AI (REGION-aiplatform.googleapis.com)
# Para Google AI Studio (geralmente usa apenas API Key):
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_ID}:generateContent?key={GEMINI_API_KEY}"
# Para Vertex AI (geralmente usa autenticação gcloud/ADC e Project ID):
# GEMINI_API_REGION = "us-central1" # Exemplo de região
# GEMINI_API_URL_VERTEX = f"https://{GEMINI_API_REGION}-aiplatform.googleapis.com/v1/projects/{GEMINI_PROJECT_ID}/locations/{GEMINI_API_REGION}/publishers/google/models/{GEMINI_MODEL_ID}:streamGenerateContent"
# Se for usar Vertex AI, a autenticação é diferente (geralmente gcloud auth application-default login) e não passaria a API Key no header assim.
# Por simplicidade, vamos focar na API do Google AI Studio primeiro.

# Configurações do Selenium
PROFILE_PATH = os.getenv("CHROME_PROFILE_PATH")  # Caminho do perfil do Chrome (se necessário)
TWITTER_BASE_URL = "https://x.com"
TWITTER_TRENDS_URL = f"{TWITTER_BASE_URL}/explore/tabs/trending"
TWITTER_HOME_URL_FOR_TWEET_BUTTON = f"{TWITTER_BASE_URL}/home"

# Outras Configurações
MAX_TWEET_CHARACTERS = 280
SCHEDULE_INTERVAL_MINUTES = 90 # Alterado para 15 para não sobrecarregar
SCREENSHOT_DIR = "screenshots_twitter_bot"

# Configuração do Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

def init_driver(profile_path):
    logging.info("Configurando opções do Chrome...")
    options = Options()
    if profile_path:
        logging.info(f"Usando perfil do Chrome em: {profile_path}")
        options.add_argument(f"user-data-dir={profile_path}")
    else:
        logging.warning("Nenhum caminho de perfil do Chrome especificado.")
    options.add_argument("--lang=pt-BR")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # options.add_argument("--headless")

    logging.info("Instalando/Obtendo ChromeDriver...")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logging.info("WebDriver inicializado com sucesso.")
        return driver
    except Exception as e:
        logging.error(f"Erro ao inicializar o WebDriver: {e}", exc_info=True)
        raise

    # Verificação (opcional, mas bom para debug inicial)
if not GEMINI_API_KEY:
    logging.error("A variável de ambiente GEMINI_API_KEY não foi encontrada. Verifique seu arquivo .env")
    # Você pode querer sair do script aqui ou lançar uma exceção
    exit("Erro: GEMINI_API_KEY não configurada.")
if not PROFILE_PATH:
    logging.warning("A variável de ambiente CHROME_PROFILE_PATH não foi encontrada. Usando None (perfil temporário).")
    # PROFILE_PATH = None # Ou defina um padrão se quiser

def get_tweet_content_from_gemini(trend_topic):
    # ... (cabeçalho da função e headers como antes) ...
    
    logging.info(f"Gerando conteúdo de tweet para o tópico via Gemini: '{trend_topic}'")
    headers = {"Content-Type": "application/json"}
    prompt = (
        f"O termo '{trend_topic}' está atualmente em alta no X (antigo Twitter). "
        f"Crie um tweet curto e engajador (máximo de {MAX_TWEET_CHARACTERS - 45} caracteres) "
        f"que compartilhe uma curiosidade interessante ou um fato pouco conhecido sobre '{trend_topic}', "
        f"considerando seu contexto como um assunto popular online. "
        # Removida a parte explícita sobre "mencionar setor" e deixado mais aberto
        f"Se o tópico envolver uma inovação, destaque brevemente seu potencial impacto. "
        f"Inclua 2 ou 3 hashtags relevantes e populares. "
        f"O tom deve ser informativo e curioso. "
        f"Não use datas/anos específicos. Não use saudações. Não inclua links. Não use colchetes [] na resposta final."
        f"Responda APENAS com o texto do tweet."
    )
    
    data_payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.50, # Um pouco menos aleatório
            "maxOutputTokens": 150,
            "topP": 0.95,
            "topK": 40
        },
        # Safety settings (opcional, mas recomendado)
        # "safetySettings": [
        #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        # ]
    }

    try:
        logging.debug(f"Enviando requisição para Gemini API URL: {GEMINI_API_URL}")
        logging.debug(f"Payload para Gemini: {json.dumps(data_payload, indent=2)}")
        response = requests.post(GEMINI_API_URL, headers=headers, json=data_payload, timeout=45) # Aumentar timeout
        
        logging.debug(f"Status da resposta da API Gemini: {response.status_code}")
        logging.debug(f"Corpo da resposta da API Gemini (bruto): {response.text[:500]}") # Logar início da resposta

        response.raise_for_status() 
        
        data = response.json()
        
        # A estrutura da resposta do Gemini é diferente
        # Verifica se 'candidates' existe e tem pelo menos um item
        if "candidates" in data and data["candidates"]:
            candidate = data["candidates"][0]
            # Verifica se 'content' e 'parts' existem
            if "content" in candidate and "parts" in candidate["content"] and candidate["content"]["parts"]:
                tweet_text = candidate["content"]["parts"][0]["text"].strip()
            else:
                logging.error(f"Estrutura inesperada na resposta do Gemini (sem content/parts): {candidate}")
                return None
        else:
            logging.error(f"Nenhum candidato retornado pela API Gemini ou estrutura inesperada. Resposta: {data}")
            # Se houver um 'promptFeedback', pode indicar bloqueio por safety settings
            if "promptFeedback" in data and "blockReason" in data["promptFeedback"]:
                logging.error(f"Prompt bloqueado pela API Gemini. Razão: {data['promptFeedback']['blockReason']}")
            return None
            
        if len(tweet_text) > MAX_TWEET_CHARACTERS:
            tweet_text = tweet_text[:MAX_TWEET_CHARACTERS-3] + "..."
            
        logging.info(f"Tweet gerado pelo Gemini: '{tweet_text}'")
        return tweet_text
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro na requisição à API Gemini: {e}")
    except (KeyError, IndexError, TypeError) as e: # TypeError para caso 'parts' não seja uma lista
        logging.error(f"Erro ao processar resposta da API Gemini: {e} - Resposta: {data if 'data' in locals() else 'N/A'}")
    except json.JSONDecodeError as e:
        logging.error(f"Erro ao decodificar JSON da resposta da API Gemini: {e} - Resposta (texto): {response.text if 'response' in locals() else 'N/A'}")
    return None


def select_trends_from_twitter(driver):
    logging.info(f"Acessando URL de trends: {TWITTER_TRENDS_URL}")
    driver.get(TWITTER_TRENDS_URL)
    wait = WebDriverWait(driver, 20)

    try:
        trends_container_xpath = (
            '//div[@aria-label="Timeline: Explore" or '
            '@aria-label="Linha do Tempo: Explorar" or '
            '@aria-label="Timeline: Trending now" or '
            '@aria-label="Timeline: Assuntos do momento"]'
        )
        trends_container = wait.until(
            EC.visibility_of_element_located((By.XPATH, trends_container_xpath))
        )
        logging.info("Contêiner de trends encontrado.")

        # XPath para os nomes das trends (o segundo div dentro de data-testid="trend" costuma ter o nome)
        # Procuramos pelo span dentro deste div.
        trend_elements_xpath = './/div[@data-testid="trend"]/div/div[2]/span'
        
        # Se o anterior não funcionar, podemos tentar ser mais genéricos, pegando todos os spans
        # e filtrando depois. No seu código original, era um XPath absoluto muito específico.
        # Este é um pouco mais robusto:
        # trend_elements_xpath_alternative = './/div[@data-testid="trend"]//span'

        # Esperar que pelo menos alguns itens de trend estejam carregados
        wait.until(EC.presence_of_all_elements_located((By.XPATH, './/div[@data-testid="trend"]')))
        
        candidate_elements = trends_container.find_elements(By.XPATH, trend_elements_xpath)
        
        trends_texts = []
        for elem in candidate_elements:
            text = elem.text.strip()
            # Filtros básicos: não vazio, não é só um número, não é só "posts", não contém "·" (separador de categoria)
            # e tem um tamanho razoável.
            if text and not text.isdigit() and \
               "posts" not in text.lower() and \
               "tweets" not in text.lower() and \
               "·" not in text and \
               len(text) > 2 and len(text) < 50: # Limite de tamanho para evitar frases longas
                trends_texts.append(text)
        
        unique_trends = list(dict.fromkeys(trends_texts)) # Remover duplicatas

        logging.info(f"Trends encontradas e pré-filtradas ({len(unique_trends)}): {unique_trends[:10]}")
        return unique_trends

    except TimeoutException:
        logging.error("Timeout ao tentar encontrar trends.")
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_selecting_trends_timeout.png"))
    except Exception as e:
        logging.error(f"Erro ao selecionar trends: {e}", exc_info=True)
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_selecting_trends_generic.png"))
    return []


def post_tweet_on_twitter(driver, tweet_content):
    logging.info("Navegando para a home para encontrar o botão de postar.")
    driver.get(TWITTER_HOME_URL_FOR_TWEET_BUTTON)
    wait = WebDriverWait(driver, 30) # Aumentar espera para home page

    try:
        post_button_xpath = "//a[@data-testid='SideNav_NewTweet_Button']"
        logging.info(f"Procurando botão de postar com XPath: {post_button_xpath}")
        post_button = wait.until(EC.element_to_be_clickable((By.XPATH, post_button_xpath)))
        # Às vezes, um scroll é necessário se o botão não estiver visível
        driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", post_button)
        time.sleep(0.5) # Pequena pausa após o scroll
        post_button.click()
        logging.info("Botão de 'Postar' clicado.")
        time.sleep(1.5) # Aumentar pausa para a caixa de diálogo abrir

        tweet_textarea_xpath = "//div[@data-testid='tweetTextarea_0']"
        logging.info(f"Procurando caixa de texto do tweet com XPath: {tweet_textarea_xpath}")
        tweet_textarea = wait.until(EC.visibility_of_element_located((By.XPATH, tweet_textarea_xpath)))
        
        logging.info(f"Inserindo texto na caixa de tweet: '{tweet_content[:50]}...'")
        tweet_textarea.send_keys(tweet_content)
        time.sleep(1)

        submit_tweet_button_xpath = "//button[@data-testid='tweetButton']"
        logging.info(f"Procurando botão de submeter o tweet com XPath: {submit_tweet_button_xpath}")
        submit_tweet_button = wait.until(EC.element_to_be_clickable((By.XPATH, submit_tweet_button_xpath)))
        
        # Garantir que o botão está visível e clicável
        driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", submit_tweet_button)
        time.sleep(0.5)
        # Tentar clicar via JavaScript se o clique normal falhar por interceptação
        try:
            submit_tweet_button.click()
        except ElementClickInterceptedException:
            logging.warning("Clique normal interceptado, tentando clique via JavaScript.")
            driver.execute_script("arguments[0].click();", submit_tweet_button)

        logging.info("Tweet postado com sucesso!")
        # Esperar por uma indicação de sucesso, como a caixa de diálogo desaparecer ou uma notificação
        # Exemplo: esperar que o botão de postar da caixa de diálogo não esteja mais visível
        wait.until(EC.invisibility_of_element_located((By.XPATH, submit_tweet_button_xpath)))
        logging.info("Caixa de diálogo de tweet fechada (indicando sucesso).")
        return True

    except TimeoutException as e:
        logging.error(f"Timeout ao tentar postar o tweet: {e}")
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_posting_tweet_timeout.png"))
    except ElementClickInterceptedException as e:
        logging.error(f"ElementClickInterceptedException ao postar: {e}")
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_posting_tweet_intercepted.png"))
    except Exception as e:
        logging.error(f"Erro inesperado ao postar tweet: {e}", exc_info=True)
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_posting_tweet_generic.png"))
    return False


def twitter_bot_task():
    logging.info("--- Iniciando tarefa do bot do Twitter ---")
    driver = None
    try:
        driver = init_driver(PROFILE_PATH)
        
        trends = select_trends_from_twitter(driver)

        if trends:
            chosen_trend = random.choice(trends)
            logging.info(f"Trend escolhida: '{chosen_trend}'")
            
            tweet_text = get_tweet_content_from_gemini(chosen_trend)
            
            if tweet_text:
                if post_tweet_on_twitter(driver, tweet_text):
                    logging.info(f"Tarefa concluída com sucesso para a trend: '{chosen_trend}'")
                else:
                    logging.warning("Falha ao postar o tweet.")
            else:
                logging.warning("Não foi possível gerar conteúdo para o tweet.")
        else:
            logging.warning("Nenhuma trend foi selecionada.")

    except Exception as e:
        logging.error(f"Erro na tarefa do bot do Twitter: {e}", exc_info=True)
        if driver:
            try:
                driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_twitter_bot_task.png"))
            except Exception: pass # Ignora erros ao salvar screenshot aqui
    finally:
        if driver:
            logging.info("Fechando o WebDriver da tarefa atual.")
            driver.quit()
        logging.info("--- Tarefa do bot do Twitter finalizada ---")


# --- AGENDAMENTO ---
logging.info(f"Agendando a tarefa para rodar a cada {SCHEDULE_INTERVAL_MINUTES} minutos.")
# Para teste inicial, você pode querer rodar uma vez imediatamente:
#twitter_bot_task() 

schedule.every(SCHEDULE_INTERVAL_MINUTES).minutes.do(twitter_bot_task)

# Para testar apenas uma vez sem o loop de agendamento:
#if __name__ == "__main__":
#    twitter_bot_task() # Executa a tarefa uma vez para teste

#Para rodar continuamente com agendamento:
if __name__ == "__main__":
    logging.info("Iniciando loop de agendamento. Pressione Ctrl+C para sair.")
    # Roda uma vez imediatamente ao iniciar
    schedule.run_all(delay_seconds=1) 
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Loop de agendamento interrompido pelo usuário.")
            break
        except Exception as e:
            logging.error(f"Erro no loop de agendamento: {e}", exc_info=True)
            time.sleep(60) # Espera um minuto antes de tentar novamente em caso de erro grave