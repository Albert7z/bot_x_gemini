# -*- coding: utf-8 -*-

# --- IMPORTS ---
import logging
import random
import time
import json
import requests
import os
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk, filedialog
import threading
from datetime import datetime, timedelta
import csv
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

import schedule
# Opcional: para usar a biblioteca oficial do Google
# import google.generativeai as genai

# Carrega variáveis do arquivo .env
load_dotenv()

# --- CONFIGURAÇÕES GLOBAIS E VERIFICAÇÕES ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_ID = "gemini-1.5-flash-latest"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_ID}:generateContent?key={GEMINI_API_KEY}"

raw_profile_path = os.getenv("CHROME_PROFILE_PATH")
PROFILE_PATH = os.path.abspath(os.path.expanduser(raw_profile_path)) if raw_profile_path else None

TWITTER_BASE_URL = "https://x.com"
TWITTER_TRENDS_URL = f"{TWITTER_BASE_URL}/explore/tabs/trending"
TWITTER_HOME_URL_FOR_TWEET_BUTTON = f"{TWITTER_BASE_URL}/home"
MAX_TWEET_CHARACTERS = 260
SCREENSHOT_DIR = "screenshots_twitter_bot"
CONFIG_FILE = "bot_config.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
logger = logging.getLogger()

if not os.path.exists(SCREENSHOT_DIR): os.makedirs(SCREENSHOT_DIR)

if not GEMINI_API_KEY:
    logger.critical("CRÍTICO: GEMINI_API_KEY não encontrada no .env!")
    messagebox.showerror("Erro Crítico", "GEMINI_API_KEY não encontrada no .env!")
    exit()

if not PROFILE_PATH or not os.path.isdir(PROFILE_PATH):
    logger.warning(f"Caminho do perfil do Chrome não encontrado ou inválido. Usando perfil temporário. Caminho fornecido: {PROFILE_PATH}")
    PROFILE_PATH = None

# --- SUA LÓGICA DE BOT (INTACTA E FUNCIONAL) ---
class BotStats:
    def __init__(self):
        self.total_tweets = 0
        self.successful_tweets = 0
        self.failed_tweets = 0
        self.start_time = None
        self.last_tweet_time = None
        self.trends_used = []
    
    def add_tweet_attempt(self, success=True, trend_used=None):
        """
        Adiciona uma tentativa de tweet às estatísticas.
        """
        self.total_tweets += 1
        
        if success:
            self.successful_tweets += 1
            self.last_tweet_time = datetime.now()
            logger.info(f"Sucesso registrado. Total sucessos: {self.successful_tweets}")
        else:
            self.failed_tweets += 1
            logger.info(f"Falha registrada. Total falhas: {self.failed_tweets}")
        
        if trend_used:
            entry = {
                'trend': trend_used,
                'timestamp': datetime.now(),
                'success': success
            }
            self.trends_used.append(entry)
            logger.debug(f"Trend registrada: {trend_used} - {'Sucesso' if success else 'Falha'}")
    
    def get_success_rate(self):
        """
        Calcula e retorna a taxa de sucesso.
        """
        if self.total_tweets == 0:
            return 0.0
        
        rate = (self.successful_tweets / self.total_tweets) * 100
        return rate
    
    def export_to_csv(self, filename):
        """
        Exporta as estatísticas para um arquivo CSV.
        """
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Trend', 'Timestamp', 'Success'])
                
                for entry in self.trends_used:
                    writer.writerow([
                        entry['trend'],
                        entry['timestamp'].strftime('%d/%m/%Y %H:%M:%S'),
                        entry['success']
                    ])
            
            logger.info(f"Estatísticas exportadas para: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao exportar estatísticas: {e}")
            return False
    
    def get_summary(self):
        """
        Retorna um resumo das estatísticas.
        """
        return {
            'total_tweets': self.total_tweets,
            'successful_tweets': self.successful_tweets,
            'failed_tweets': self.failed_tweets,
            'success_rate': self.get_success_rate(),
            'uptime': str(datetime.now() - self.start_time).split('.')[0] if self.start_time else "N/A",
            'last_tweet_time': self.last_tweet_time.strftime('%H:%M:%S') if self.last_tweet_time else "N/A"
        }

def init_driver(profile_path_arg):
    options = Options()
    if profile_path_arg: options.add_argument(f"user-data-dir={profile_path_arg}")
    options.add_argument("--lang=pt-BR"); options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications"); options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage")
    try:
        service = Service(ChromeDriverManager().install()); return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"Falha ao inicializar o WebDriver: {e}", exc_info=True); raise

def get_tweet_content_from_gemini(trend_topic, custom_prompt=None):
    """
    Versão melhorada da função para obter conteúdo da IA Gemini.
    """
    logger.info(f"Solicitando conteúdo da IA Gemini para trend: '{trend_topic}'")
    
    headers = {"Content-Type": "application/json"}
    
    # Usa prompt personalizado se fornecido, senão usa o padrão
    if custom_prompt and custom_prompt.strip():
        prompt = custom_prompt.replace("{trend}", trend_topic)
        logger.info("Usando prompt personalizado")
    else:
        prompt = (f"'{trend_topic}' está em alta. Crie um tweet curto e engajador "
                 f"(máximo de {MAX_TWEET_CHARACTERS - 45} caracteres) com uma curiosidade "
                 f"sobre o tema. Inclua 1 hashtag relevante. Tom informativo. "
                 f"Não use datas, saudações, links ou []. Responda APENAS com o texto do tweet.")
        logger.info("Usando prompt padrão")
    
    data_payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 100,
            "topP": 0.8,
            "topK": 10
        }
    }
    
    try:
        logger.info("Enviando requisição para API Gemini...")
        response = requests.post(
            GEMINI_API_URL,
            headers=headers,
            json=data_payload,
            timeout=45
        )
        
        logger.info(f"Status da resposta: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        # Verifica se a resposta tem o formato esperado
        if not data.get("candidates"):
            logger.error("Resposta da API sem candidates")
            return None
            
        candidate = data["candidates"][0]
        if not candidate.get("content", {}).get("parts"):
            logger.error("Resposta da API sem content/parts")
            return None
        
        generated_text = candidate["content"]["parts"][0]["text"].strip()
        
        if not generated_text:
            logger.error("Texto gerado está vazio")
            return None
        
        logger.info(f"✓ Conteúdo gerado com sucesso: '{generated_text[:50]}...'")
        return generated_text
        
    except requests.exceptions.Timeout:
        logger.error("Timeout na requisição para API Gemini")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"Erro HTTP na API Gemini: {e}")
        try:
            error_data = response.json()
            logger.error(f"Detalhes do erro: {error_data}")
        except:
            pass
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de rede na API Gemini: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado na API Gemini: {e}", exc_info=True)
        return None

def select_trends_from_twitter(driver):
    """
    Seleciona trends do Twitter com melhor tratamento de erros e múltiplos seletores.
    """
    logger.info(f"Acessando a página de trends: {TWITTER_TRENDS_URL}")
    
    try:
        # Navega para a página de trends
        driver.get(TWITTER_TRENDS_URL)
        
        # Aguarda a página carregar
        wait = WebDriverWait(driver, 30)
        
        # Aguarda um elemento que indica que a página carregou
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # Aguarda mais um pouco para garantir que o conteúdo dinâmico carregou
        time.sleep(5)
        
        logger.info("Página de trends carregada, procurando por trends...")
        
        trends = []
        
        # Múltiplas estratégias para encontrar trends
        strategies = [
            # Estratégia 1: Usando data-testid
            {
                'name': 'data-testid',
                'container': "//section[@aria-labelledby]",
                'elements': ".//div[@data-testid='trend']//span"
            },
            # Estratégia 2: Procurando por texto que começa com #
            {
                'name': 'hashtag_spans',
                'container': "//main",
                'elements': ".//span[starts-with(text(), '#')]"
            },
            # Estratégia 3: Procurando em divs de trend
            {
                'name': 'trend_divs',
                'container': "//div[contains(@aria-label, 'Timeline')]",
                'elements': ".//div[contains(@class, 'trend') or contains(@data-testid, 'trend')]//span"
            },
            # Estratégia 4: Procura mais ampla por spans com #
            {
                'name': 'all_hashtags',
                'container': "//body",
                'elements': ".//span[contains(text(), '#')]"
            }
        ]
        
        for strategy in strategies:
            try:
                logger.info(f"Tentando estratégia: {strategy['name']}")
                
                # Tenta encontrar o container
                container = None
                try:
                    container = wait.until(EC.presence_of_element_located((By.XPATH, strategy['container'])))
                    logger.info(f"Container encontrado para estratégia {strategy['name']}")
                except TimeoutException:
                    logger.warning(f"Container não encontrado para estratégia {strategy['name']}")
                    continue
                
                # Procura pelos elementos dentro do container
                elements = container.find_elements(By.XPATH, strategy['elements'])
                logger.info(f"Encontrados {len(elements)} elementos na estratégia {strategy['name']}")
                
                # Extrai o texto dos elementos
                strategy_trends = []
                for element in elements:
                    try:
                        text = element.text.strip()
                        if text and text.startswith('#') and len(text) > 1:
                            # Remove caracteres especiais e espaços extras
                            clean_text = text.split()[0]  # Pega apenas a primeira palavra
                            if len(clean_text) > 1 and clean_text not in strategy_trends:
                                strategy_trends.append(clean_text)
                    except Exception as e:
                        continue
                
                if strategy_trends:
                    logger.info(f"Estratégia {strategy['name']} encontrou {len(strategy_trends)} trends")
                    trends.extend(strategy_trends)
                    break  # Se encontrou trends, para aqui
                    
            except Exception as e:
                logger.warning(f"Erro na estratégia {strategy['name']}: {e}")
                continue
        
        # Remove duplicatas mantendo a ordem
        unique_trends = []
        seen = set()
        for trend in trends:
            if trend not in seen:
                unique_trends.append(trend)
                seen.add(trend)
        
        trends = unique_trends[:20]  # Limita a 20 trends
        
        if trends:
            logger.info(f"Trends encontradas ({len(trends)}): {trends[:10]}...")  # Mostra apenas as 10 primeiras no log
            
            # Salva screenshot de sucesso
            success_screenshot = os.path.join(SCREENSHOT_DIR, f"trends_success_{int(time.time())}.png")
            driver.save_screenshot(success_screenshot)
            
        else:
            logger.warning("Nenhuma trend foi encontrada com nenhuma das estratégias")
            
            # Tira screenshot para debug
            error_screenshot = os.path.join(SCREENSHOT_DIR, f"no_trends_{int(time.time())}.png")
            driver.save_screenshot(error_screenshot)
            
            # Tenta logar o HTML da página para debug
            try:
                page_source_snippet = driver.page_source[:2000]  # Primeiros 2000 caracteres
                logger.debug(f"Snippet do HTML da página: {page_source_snippet}")
            except:
                pass
                
        return trends
        
    except Exception as e:
        logger.error(f"Erro geral ao selecionar trends: {e}", exc_info=True)
        
        # Tira screenshot do erro
        error_screenshot = os.path.join(SCREENSHOT_DIR, f"trends_error_{int(time.time())}.png")
        try:
            driver.save_screenshot(error_screenshot)
            logger.error(f"Screenshot do erro salvo em: {error_screenshot}")
        except:
            pass
        
        return []


def get_backup_trends():
    """
    Retorna uma lista de trends de backup caso não consiga obter do Twitter.
    """
    backup_trends = [
        "#Python", "#JavaScript", "#TechNews", "#AI", "#MachineLearning",
        "#WebDev", "#Programming", "#OpenSource", "#DataScience", "#CloudComputing",
        "#Cybersecurity", "#Innovation", "#DigitalTransformation", "#SoftwareDevelopment",
        "#TechTrends", "#Automation", "#BigData", "#IoT", "#Blockchain", "#DevOps"
    ]
    return backup_trends

def post_tweet_on_twitter(driver, tweet_content):
    """
    Posta um tweet no Twitter com melhor tratamento de erros e diagnóstico.
    """
    logger.info(f"Tentando postar tweet: '{tweet_content[:50]}...'")
    
    try:
        # Navega para a página inicial do Twitter
        driver.get(TWITTER_HOME_URL_FOR_TWEET_BUTTON)
        logger.info("Navegou para página inicial do Twitter")
        
        # Aguarda a página carregar completamente
        wait = WebDriverWait(driver, 30)
        
        # Tenta encontrar e clicar no botão de novo tweet
        logger.info("Procurando botão de novo tweet...")
        
        # Múltiplos seletores possíveis para o botão de tweet
        tweet_button_selectors = [
            "//a[@data-testid='SideNav_NewTweet_Button']",
            "//button[@data-testid='SideNav_NewTweet_Button']",
            "//a[contains(@href, '/compose/tweet')]",
            "//button[contains(text(), 'Tweet')]",
            "//a[@aria-label='Tweet']"
        ]
        
        tweet_button = None
        for selector in tweet_button_selectors:
            try:
                tweet_button = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                logger.info(f"Botão de tweet encontrado com seletor: {selector}")
                break
            except TimeoutException:
                continue
        
        if not tweet_button:
            raise Exception("Não foi possível encontrar o botão de novo tweet")
        
        # Clica no botão de tweet
        try:
            tweet_button.click()
            logger.info("Clicou no botão de novo tweet")
        except ElementClickInterceptedException:
            logger.warning("Clique interceptado, tentando com JavaScript")
            driver.execute_script("arguments[0].click();", tweet_button)
        
        # Aguarda a área de texto aparecer
        logger.info("Procurando área de texto do tweet...")
        
        # Múltiplos seletores para a área de texto
        textarea_selectors = [
            "//div[@data-testid='tweetTextarea_0']",
            "//div[@role='textbox']",
            "//div[@contenteditable='true']",
            "//div[contains(@class, 'public-DraftEditor-content')]"
        ]
        
        tweet_area = None
        for selector in textarea_selectors:
            try:
                tweet_area = wait.until(EC.visibility_of_element_located((By.XPATH, selector)))
                logger.info(f"Área de texto encontrada com seletor: {selector}")
                break
            except TimeoutException:
                continue
        
        if not tweet_area:
            # Tira screenshot para debug
            screenshot_path = os.path.join(SCREENSHOT_DIR, f"no_textarea_{int(time.time())}.png")
            driver.save_screenshot(screenshot_path)
            raise Exception(f"Não foi possível encontrar a área de texto. Screenshot salvo em: {screenshot_path}")
        
        # Limpa qualquer texto existente e insere o novo conteúdo
        tweet_area.clear()
        tweet_area.send_keys(tweet_content)
        logger.info("Texto inserido na área de tweet")
        
        # Aguarda um pouco para garantir que o texto foi inserido
        time.sleep(2)
        
        # Verifica se o texto foi realmente inserido
        inserted_text = tweet_area.text or tweet_area.get_attribute('value') or ''
        if not inserted_text.strip():
            raise Exception("O texto do tweet não foi inserido corretamente")
        
        logger.info(f"Texto verificado na área: '{inserted_text[:50]}...'")
        
        # Procura pelo botão de publicar
        logger.info("Procurandoботão de publicar...")
        
        # Múltiplos seletores para o botão de publicar
        submit_selectors = [
            "//button[@data-testid='tweetButton']",
            "//button[@data-testid='tweetButtonInline']",
            "//button[contains(text(), 'Tweet')]",
            "//button[contains(text(), 'Postar')]",
            "//button[@role='button'][contains(., 'Tweet')]"
        ]
        
        submit_button = None
        for selector in submit_selectors:
            try:
                submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                logger.info(f"Botão de publicar encontrado com seletor: {selector}")
                break
            except TimeoutException:
                continue
        
        if not submit_button:
            # Tira screenshot para debug
            screenshot_path = os.path.join(SCREENSHOT_DIR, f"no_submit_button_{int(time.time())}.png")
            driver.save_screenshot(screenshot_path)
            raise Exception(f"Não foi possível encontrar o botão de publicar. Screenshot salvo em: {screenshot_path}")
        
        # Verifica se o botão está habilitado
        if not submit_button.is_enabled():
            raise Exception("O botão de publicar está desabilitado")
        
        # Clica no botão de publicar
        try:
            submit_button.click()
            logger.info("Clicou no botão de publicar")
        except ElementClickInterceptedException:
            logger.warning("Clique no botão de publicar interceptado, tentando com JavaScript")
            driver.execute_script("arguments[0].click();", submit_button)
        
        # Aguarda a confirmação de que o tweet foi enviado
        logger.info("Aguardando confirmação do envio...")
        
        # Verifica se o modal de composição foi fechado (indicando sucesso)
        try:
            wait.until(EC.invisibility_of_element_located((By.XPATH, "//div[@data-testid='tweetTextarea_0']")))
            logger.info("Modal de composição fechado - tweet enviado com sucesso")
        except TimeoutException:
            # Se o modal não fechou, pode ter havido um erro
            logger.warning("Modal de composição não fechou - verificando possíveis erros")
            
            # Procura por mensagens de erro
            error_selectors = [
                "//div[@role='alert']",
                "//div[contains(@class, 'error')]",
                "//div[contains(text(), 'erro')]",
                "//div[contains(text(), 'Error')]"
            ]
            
            for selector in error_selectors:
                try:
                    error_element = driver.find_element(By.XPATH, selector)
                    error_text = error_element.text
                    if error_text:
                        raise Exception(f"Erro detectado na interface: {error_text}")
                except:
                    continue
        
        # Aguarda mais um pouco para garantir que o tweet foi processado
        time.sleep(3)
        
        # Tira screenshot de sucesso
        success_screenshot = os.path.join(SCREENSHOT_DIR, f"tweet_success_{int(time.time())}.png")
        driver.save_screenshot(success_screenshot)
        
        logger.info(f"Tweet postado com sucesso! Screenshot salvo em: {success_screenshot}")
        return True
        
    except TimeoutException as e:
        error_msg = f"Timeout ao postar tweet: {str(e)}"
        logger.error(error_msg)
        
        # Tira screenshot do erro
        error_screenshot = os.path.join(SCREENSHOT_DIR, f"timeout_error_{int(time.time())}.png")
        driver.save_screenshot(error_screenshot)
        logger.error(f"Screenshot do erro salvo em: {error_screenshot}")
        
        return False
        
    except Exception as e:
        error_msg = f"Erro ao postar tweet: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Tira screenshot do erro
        error_screenshot = os.path.join(SCREENSHOT_DIR, f"post_error_{int(time.time())}.png")
        driver.save_screenshot(error_screenshot)
        logger.error(f"Screenshot do erro salvo em: {error_screenshot}")
        
        # Tenta obter informações adicionais sobre o estado da página
        try:
            current_url = driver.current_url
            page_title = driver.title
            logger.error(f"Estado da página - URL: {current_url}, Título: {page_title}")
        except:
            pass
        
        return False

# --- ESTRUTURA DE CONTROLE DA GUI E AGENDADOR (CORRIGIDA) ---
bot_is_running_event = threading.Event()
stop_scheduler_event = threading.Event()
bot_thread, bot_stats, current_interval = None, BotStats(), 90
next_execution_time = None # Variável global para controlar o próximo horário

class TkinterLogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__(); self.text_widget = text_widget
    def emit(self, record):
        msg = self.format(record); self.text_widget.after(0, self.append_message, msg)
    def append_message(self, msg):
        if not self.text_widget or not self.text_widget.winfo_exists(): return
        self.text_widget.configure(state='normal')
        if "ERROR" in msg or "CRITICAL" in msg: tag = 'error'
        elif "WARNING" in msg: tag = 'warning'
        else: tag = 'info'
        self.text_widget.insert(tk.END, msg + '\n', tag); self.text_widget.configure(state='disabled')
        if autoscroll_var.get(): self.text_widget.see(tk.END)

def load_config():
    global current_interval
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f: config = json.load(f)
            current_interval = config.get('interval', 90); return config
    except Exception as e: logger.error(f"Erro ao carregar config: {e}")
    return {'interval': 90, 'custom_prompt': ''}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f: json.dump(config, f, indent=2)

def twitter_bot_task_thread_safe():
    """
    Função principal do bot com melhor tratamento de erros e logging detalhado.
    """
    global bot_stats
    
    logger.info("=" * 50)
    logger.info("INICIANDO NOVO CICLO DO BOT")
    logger.info("=" * 50)
    
    driver = None
    chosen_trend = None
    success = False
    error_details = None
    
    try:
        # Etapa 1: Inicialização do driver
        logger.info("Etapa 1/5: Inicializando o WebDriver...")
        driver = init_driver(PROFILE_PATH)
        logger.info("✓ WebDriver inicializado com sucesso")
        
        # Etapa 2: Seleção de trends
        logger.info("Etapa 2/5: Obtendo trends do Twitter...")
        trends = select_trends_from_twitter(driver)
        
        if not trends:
            logger.warning("Nenhuma trend obtida do Twitter, usando trends de backup...")
            trends = get_backup_trends()
            logger.info(f"Usando {len(trends)} trends de backup")
        
        if not trends:
            raise Exception("Não foi possível obter nenhuma trend (nem do Twitter nem de backup)")
        
        # Seleciona uma trend aleatória
        chosen_trend = random.choice(trends)
        logger.info(f"✓ Trend selecionada: '{chosen_trend}' (de {len(trends)} disponíveis)")
        
        # Etapa 3: Geração de conteúdo
        logger.info("Etapa 3/5: Gerando conteúdo com IA Gemini...")
        custom_prompt = load_config().get('custom_prompt', '')
        tweet_text = get_tweet_content_from_gemini(chosen_trend, custom_prompt)
        
        if not tweet_text:
            raise Exception("Falha ao gerar conteúdo com a IA Gemini")
        
        # Valida o tamanho do tweet
        if len(tweet_text) > MAX_TWEET_CHARACTERS:
            logger.warning(f"Tweet muito longo ({len(tweet_text)} chars), truncando...")
            tweet_text = tweet_text[:MAX_TWEET_CHARACTERS-3] + "..."
        
        logger.info(f"✓ Conteúdo gerado ({len(tweet_text)} chars): '{tweet_text[:100]}...'")
        
        # Etapa 4: Postagem do tweet
        logger.info("Etapa 4/5: Postando tweet no Twitter...")
        success = post_tweet_on_twitter(driver, tweet_text)
        
        if success:
            logger.info("✓ Tweet postado com sucesso!")
        else:
            error_details = "Falha na postagem do tweet"
            logger.error(f"✗ {error_details}")
        
        # Etapa 5: Finalização
        logger.info("Etapa 5/5: Finalizando ciclo...")
        
    except Exception as e:
        error_details = str(e)
        logger.error(f"✗ Erro geral na tarefa: {error_details}", exc_info=True)
        
        # Tenta obter informações adicionais do driver se ainda estiver ativo
        if driver:
            try:
                current_url = driver.current_url
                logger.error(f"URL atual quando ocorreu o erro: {current_url}")
            except:
                pass
    
    finally:
        # Sempre registra a tentativa nas estatísticas
        bot_stats.add_tweet_attempt(success, chosen_trend)
        
        # Atualiza a interface
        try:
            app_tk.after(0, update_stats_display)
            app_tk.after(0, update_history_tree)
        except:
            pass
        
        # Fecha o driver
        if driver:
            try:
                driver.quit()
                logger.info("✓ WebDriver fechado")
            except Exception as e:
                logger.warning(f"Erro ao fechar WebDriver: {e}")
        
        # Log de finalização
        logger.info("=" * 50)
        if success:
            logger.info(f"CICLO CONCLUÍDO COM SUCESSO - Trend: {chosen_trend}")
        else:
            logger.error(f"CICLO FALHOU - Trend: {chosen_trend}, Erro: {error_details}")
        logger.info("=" * 50)

def lancar_e_reagendar_tarefa():
    """Lança a tarefa em uma thread e recalcula o próximo horário de execução."""
    global next_execution_time
    
    # Lança a tarefa principal em segundo plano
    threading.Thread(target=twitter_bot_task_thread_safe, daemon=True).start()
    
    # Recalcula e define o próximo horário de execução a partir de AGORA
    next_execution_time = datetime.now() + timedelta(minutes=current_interval)
    logger.info(f"Tarefa executada. Próxima execução agendada para: {next_execution_time.strftime('%H:%M:%S')}")

def scheduler_loop():
    """Nosso próprio agendador, sem a biblioteca 'schedule'."""
    logger.info(f"Agendador iniciado com intervalo de {current_interval} minutos.")
    
    # Primeira execução imediata
    lancar_e_reagendar_tarefa()
    
    while not stop_scheduler_event.is_set():
        # Verifica a cada segundo
        if bot_is_running_event.is_set() and datetime.now() >= next_execution_time:
            logger.info("Horário agendado atingido. Executando tarefa...")
            lancar_e_reagendar_tarefa()
        
        stop_scheduler_event.wait(timeout=1)
        
    logger.info("Agendador finalizado.")

def apply_interval_change():
    """Aplica a mudança de intervalo e recalcula o próximo horário se o bot estiver rodando."""
    global current_interval, next_execution_time
    
    try:
        # 1. Pega o novo valor da caixa de texto da interface.
        new_interval_str = interval_var.get()
        if not new_interval_str.isdigit():
            # Se não for um número, reverte para o valor atual e sai.
            interval_var.set(str(current_interval))
            return

        new_interval = int(new_interval_str)
        if new_interval < 5:
            new_interval = 5
            interval_var.set("5")
        
        # 2. Compara com o valor global ATUAL.
        if new_interval != current_interval:
            logger.info(f"Intervalo alterado de {current_interval} para {new_interval} minutos.")
            
            # 3. ATUALIZA a variável global.
            current_interval = new_interval
            
            # 4. SALVA a nova configuração no arquivo.
            # Não chama load_config() aqui para não sobrescrever a mudança.
            config_to_save = {'interval': current_interval, 'custom_prompt': load_config().get('custom_prompt', '')}
            save_config(config_to_save)
            
            # 5. Se o bot estiver rodando, RECALCULA o próximo horário.
            if bot_is_running_event.is_set():
                next_execution_time = datetime.now() + timedelta(minutes=current_interval)
                logger.info(f"Próxima execução recalculada para: {next_execution_time.strftime('%H:%M:%S')}")
                
                # 6. Força a atualização do display para mostrar a nova contagem imediatamente.
                update_next_run_display()
                
    except Exception as e:
        logger.error(f"Erro ao aplicar o intervalo: {e}")
        interval_var.set(str(current_interval))

        
def start_bot_action():
    global bot_thread, bot_stats
    if bot_is_running_event.is_set(): return
    
    apply_interval_change()
    bot_is_running_event.set(); stop_scheduler_event.clear()
    bot_stats = BotStats(); bot_stats.start_time = datetime.now()
    
    update_stats_display()
    status_label.config(text="Status: Rodando", foreground="green"); start_button.config(state=tk.DISABLED)
    stop_button.config(state=tk.NORMAL); run_once_button.config(state=tk.NORMAL)
    
    logger.info(f"Bot iniciado com intervalo de {current_interval} minutos.")
    bot_thread = threading.Thread(target=scheduler_loop, daemon=True); bot_thread.start()
    
    # Inicia o ciclo de atualização do display
    update_next_run_display()

def stop_bot_action():
    global next_execution_time
    if not bot_is_running_event.is_set(): return
    
    bot_is_running_event.clear(); stop_scheduler_event.set()
    next_execution_time = None # Limpa o horário
    
    status_label.config(text="Status: Parando...", foreground="orange")
    app_tk.after(100, check_bot_stopped)

def check_bot_stopped():
    global bot_thread
    if bot_thread and bot_thread.is_alive():
        app_tk.after(500, check_bot_stopped); return
    
    status_label.config(text="Status: Parado", foreground="red"); start_button.config(state=tk.NORMAL)
    stop_button.config(state=tk.DISABLED)
    next_run_label.config(text="Próxima Execução: N/A")
    logger.info("Bot parado completamente."); bot_thread = None

def run_once_action():
    """Executa a tarefa uma vez e REINICIA o contador de tempo."""
    logger.info("Executando tarefa manualmente...")
    # A própria função de lançamento já reinicia o contador de tempo
    lancar_e_reagendar_tarefa()

def update_next_run_display():
    if not bot_is_running_event.is_set(): 
        # Garante que o texto esteja como N/A quando o bot não está rodando.
        next_run_label.config(text="Próxima Execução: N/A")
        return
    
    try:
        if next_execution_time:
            # Calcula o tempo restante
            time_remaining = next_execution_time - datetime.now()
            
            if time_remaining.total_seconds() > 0:
                # Formata a contagem regressiva
                minutes, seconds = divmod(int(time_remaining.total_seconds()), 60)
                next_run_label.config(text=f"Próxima: {next_execution_time.strftime('%H:%M:%S')} (em {minutes:02d}m {seconds:02d}s)")
            else:
                # Se o tempo já passou, significa que uma tarefa está em andamento
                next_run_label.config(text="Próxima: Executando agora...")
        else:
            # Se a variável de tempo ainda não foi definida
            next_run_label.config(text="Próxima: Calculando...")
    except Exception as e:
        next_run_label.config(text="Próxima: Erro no display")
        logger.error(f"Erro no display da próxima execução: {e}")
    
    # Reagende a próxima atualização do display a cada segundo
    app_tk.after(1000, update_next_run_display)

def update_stats_display():
    """
    Atualiza o display das estatísticas com correção na barra de progresso.
    """
    if not bot_stats.start_time:
        return
    
    # Calcula o tempo ativo
    uptime = str(datetime.now() - bot_stats.start_time).split('.')[0]
    
    # Calcula a taxa de sucesso
    rate = bot_stats.get_success_rate()
    
    # Monta o texto das estatísticas
    stats_text = (
        f"Tempo Ativo: {uptime}\n"
        f"Total: {bot_stats.total_tweets} | "
        f"Sucesso: {bot_stats.successful_tweets} | "
        f"Falhas: {bot_stats.failed_tweets}\n"
        f"Taxa de Sucesso: {rate:.1f}%"
    )
    
    if bot_stats.last_tweet_time:
        stats_text += f"\nÚltimo Tweet: {bot_stats.last_tweet_time.strftime('%H:%M:%S')}"
    
    # Atualiza o widget de texto das estatísticas
    try:
        stats_text_widget.config(state='normal')
        stats_text_widget.delete(1.0, tk.END)
        stats_text_widget.insert(1.0, stats_text)
        stats_text_widget.config(state='disabled')
    except Exception as e:
        logger.error(f"Erro ao atualizar texto das estatísticas: {e}")
    
    # Atualiza a barra de progresso
    try:
        # Define o valor da barra de progresso (0-100)
        success_progress['value'] = rate
        
        # Força a atualização visual da barra
        success_progress.update()
        
        # Atualiza o label da taxa de sucesso
        success_label.config(text=f"{rate:.1f}% ({bot_stats.successful_tweets}/{bot_stats.total_tweets})")
        
        # Log para debug
        logger.debug(f"Estatísticas atualizadas - Taxa: {rate:.1f}%, Total: {bot_stats.total_tweets}, Sucessos: {bot_stats.successful_tweets}")
        
    except Exception as e:
        logger.error(f"Erro ao atualizar barra de progresso: {e}")


def update_history_tree():
    """
    Atualiza a árvore do histórico com melhor tratamento de erros.
    """
    try:
        # Limpa os itens existentes
        for item in history_tree.get_children():
            history_tree.delete(item)
        
        # Adiciona os novos itens (últimos 50, em ordem reversa)
        for info in reversed(bot_stats.trends_used[-50:]):
            try:
                tags = ('success',) if info['success'] else ('fail',)
                status_symbol = "✓" if info['success'] else "✗"
                
                history_tree.insert('', 'end', values=(
                    info['trend'],
                    info['timestamp'].strftime('%H:%M:%S'),
                    status_symbol
                ), tags=tags)
            except Exception as e:
                logger.error(f"Erro ao inserir item no histórico: {e}")
                
    except Exception as e:
        logger.error(f"Erro ao atualizar árvore do histórico: {e}")


# Função auxiliar para testar as estatísticas
def test_stats_update():
    """
    Função para testar se as estatísticas estão sendo atualizadas corretamente.
    """
    logger.info("Testando atualização das estatísticas...")
    
    # Simula algumas estatísticas para teste
    if not bot_stats.start_time:
        bot_stats.start_time = datetime.now() - timedelta(minutes=10)
    
    # Adiciona algumas tentativas de teste
    bot_stats.add_tweet_attempt(True, "#TesteTrend1")
    bot_stats.add_tweet_attempt(True, "#TesteTrend2")
    bot_stats.add_tweet_attempt(False, "#TesteTrend3")
    
    # Atualiza os displays
    update_stats_display()
    update_history_tree()
    
    logger.info(f"Teste concluído - Taxa atual: {bot_stats.get_success_rate():.1f}%")

def update_history_tree():
    for item in history_tree.get_children(): history_tree.delete(item)
    for info in reversed(bot_stats.trends_used[-50:]):
        tags = ('success',) if info['success'] else ('fail',)
        history_tree.insert('', 'end', values=(info['trend'], info['timestamp'].strftime('%H:%M:%S'), "✓" if info['success'] else "✗"), tags=tags)

def clear_logs(): log_text.config(state='normal'); log_text.delete(1.0, tk.END); log_text.config(state='disabled')
def export_stats():
    if not bot_stats.trends_used: messagebox.showwarning("Aviso", "Nenhuma estatística para exportar."); return
    filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
    if filename: bot_stats.export_to_csv(filename); messagebox.showinfo("Sucesso", f"Exportado para {filename}")

def open_settings():
    win = tk.Toplevel(app_tk); win.title("Configurações"); win.transient(app_tk); win.grab_set()
    ttk.Label(win, text="Prompt Personalizado ({trend}):").pack(pady=5)
    config = load_config(); prompt_text = tk.Text(win, height=10, width=60); prompt_text.pack(padx=10, pady=5)
    prompt_text.insert(1.0, config.get('custom_prompt', ''))
    def save():
        config['custom_prompt'] = prompt_text.get(1.0, tk.END).strip(); save_config(config)
        messagebox.showinfo("Sucesso", "Configurações salvas!", parent=win); win.destroy()
    btn_frame = ttk.Frame(win); btn_frame.pack(pady=10)
    ttk.Button(btn_frame, text="Salvar", command=save).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side=tk.LEFT, padx=5)

def on_closing():
    if messagebox.askokcancel("Sair", "Deseja fechar o bot?"):
        if bot_is_running_event.is_set(): stop_bot_action()
        app_tk.destroy()

# --- CONSTRUÇÃO DA INTERFACE GRÁFICA ---
app_tk = tk.Tk(); app_tk.title("Bot de Twitter com IA Gemini"); app_tk.geometry("1000x750"); app_tk.minsize(900, 700)
app_tk.protocol("WM_DELETE_WINDOW", on_closing)
style = ttk.Style(); style.theme_use('clam'); style.configure('TNotebook.Tab', font=('Arial', 10, 'bold'))
style.configure("success.Treeview", background="#e8f5e9"); style.configure("fail.Treeview", background="#ffebee")
style.map("success.Treeview", background=[('selected', '#4caf50')]); style.map("fail.Treeview", background=[('selected', '#f44336')])

notebook = ttk.Notebook(app_tk); notebook.pack(fill="both", expand=True, padx=10, pady=10)
main_tab = ttk.Frame(notebook); notebook.add(main_tab, text="Controle Principal")
control_frame = ttk.LabelFrame(main_tab, text="Controles", padding=(15, 10)); control_frame.pack(padx=10, pady=10, fill="x")
btn_frame1 = ttk.Frame(control_frame); btn_frame1.pack(fill="x", pady=5)
start_button = ttk.Button(btn_frame1, text="▶ Iniciar Bot", command=start_bot_action); start_button.pack(side=tk.LEFT, padx=5)
stop_button = ttk.Button(btn_frame1, text="⏹ Parar Bot", command=stop_bot_action, state=tk.DISABLED); stop_button.pack(side=tk.LEFT, padx=5)
run_once_button = ttk.Button(btn_frame1, text="⏩ Executar Agora", command=run_once_action); run_once_button.pack(side=tk.LEFT, padx=5)
interval_frame = ttk.Frame(control_frame); interval_frame.pack(fill="x", pady=5)
ttk.Label(interval_frame, text="Intervalo (min):").pack(side=tk.LEFT, padx=5)
interval_var = tk.StringVar(); interval_entry = ttk.Entry(interval_frame, textvariable=interval_var, width=10)
interval_entry.pack(side=tk.LEFT)
lambda e: apply_interval_change()
ttk.Button(interval_frame, text="Aplicar", command=apply_interval_change).pack(side=tk.LEFT, padx=5)
status_frame = ttk.LabelFrame(main_tab, text="Status", padding=(15, 10)); status_frame.pack(padx=10, pady=5, fill="x")
status_label = ttk.Label(status_frame, text="Status: Parado", foreground="red", font=("Arial", 10, "bold")); status_label.pack(side=tk.LEFT, padx=5)
next_run_label = ttk.Label(status_frame, text="Próxima Execução: N/A", font=("Arial", 10)); next_run_label.pack(side=tk.LEFT, padx=20)
log_frame = ttk.LabelFrame(main_tab, text="Log de Atividades", padding=(15, 10)); log_frame.pack(padx=10, pady=10, fill="both", expand=True)
log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', height=12); log_text.pack(padx=5, pady=5, fill="both", expand=True)
log_text.tag_config('error', foreground='#d32f2f', font=('Arial', 9, 'bold')); log_text.tag_config('warning', foreground='#ff8f00'); log_text.tag_config('info', foreground='#0277bd')

stats_tab = ttk.Frame(notebook); notebook.add(stats_tab, text="📊 Estatísticas")
stats_text_widget = tk.Text(stats_tab, height=7, state='disabled', font=("Courier", 11), bg="#f0f0f0", borderwidth=0); stats_text_widget.pack(padx=10, pady=10, fill="x")
progress_frame = ttk.LabelFrame(stats_tab, text="Taxa de Sucesso", padding=(15, 10)); progress_frame.pack(padx=10, pady=10, fill="x")
success_progress = ttk.Progressbar(progress_frame, length=400, mode='determinate'); success_progress.pack(pady=10)
success_label = ttk.Label(progress_frame, text="0.0% (0/0)"); success_label.pack()

history_tab = ttk.Frame(notebook); notebook.add(history_tab, text="🕒 Histórico")
history_tree = ttk.Treeview(history_tab, columns=('Trend', 'Hora', 'Status'), show='headings', height=15); history_tree.pack(padx=10, pady=10, fill="both", expand=True)
history_tree.heading('Trend', text='Trend'); history_tree.heading('Hora', text='Hora'); history_tree.heading('Status', text='Status')
history_tree.column('Trend', width=400); history_tree.column('Hora', width=150, anchor='center'); history_tree.column('Status', width=100, anchor='center')

advanced_tab = ttk.Frame(notebook); notebook.add(advanced_tab, text="⚙️ Configurações")
autoscroll_var = tk.BooleanVar(value=True); ttk.Checkbutton(advanced_tab, text="Auto-scroll dos logs", variable=autoscroll_var).pack(anchor="w", pady=2, padx=10)

if __name__ == "__main__":
    gui_log_handler = TkinterLogHandler(log_text); gui_log_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(gui_log_handler)
    config_on_start = load_config(); interval_var.set(str(config_on_start.get('interval', 90)))
    
    tool_frame = ttk.Frame(control_frame); tool_frame.pack(fill="x", pady=(10, 5))
    ttk.Button(tool_frame, text="🧹 Limpar Logs", command=clear_logs).pack(side=tk.LEFT, padx=5)
    ttk.Button(tool_frame, text="📊 Exportar Stats", command=export_stats).pack(side=tk.LEFT, padx=5)
    ttk.Button(tool_frame, text="⚙️ Config. Prompt", command=open_settings).pack(side=tk.LEFT, padx=5)
    logger.info("Interface iniciada. Aguardando comandos.")
    app_tk.mainloop()
    if bot_thread and bot_thread.is_alive():
        stop_scheduler_event.set(); bot_is_running_event.clear(); bot_thread.join(timeout=2)