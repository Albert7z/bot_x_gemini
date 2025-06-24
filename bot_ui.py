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
        self.total_tweets, self.successful_tweets, self.failed_tweets = 0, 0, 0
        self.start_time, self.last_tweet_time = None, None
        self.trends_used = []
    def add_tweet_attempt(self, success=True, trend_used=None):
        self.total_tweets += 1
        if success: self.successful_tweets += 1; self.last_tweet_time = datetime.now()
        else: self.failed_tweets += 1
        if trend_used: self.trends_used.append({'trend': trend_used, 'timestamp': datetime.now(), 'success': success})
    def get_success_rate(self):
        return (self.successful_tweets / self.total_tweets * 100) if self.total_tweets else 0
    def export_to_csv(self, filename):
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f); writer.writerow(['Trend', 'Timestamp', 'Success'])
            for entry in self.trends_used: writer.writerow([entry['trend'], entry['timestamp'].strftime('%d/%m/%Y %H:%M:%S'), entry['success']])

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
    headers = {"Content-Type": "application/json"}
    prompt = custom_prompt.replace("{trend}", trend_topic) if custom_prompt else (f"'{trend_topic}' está em alta. Crie um tweet curto e engajador (máx de {MAX_TWEET_CHARACTERS - 45} caracteres) com uma curiosidade sobre o tema. Inclua 1 hashtag relevante. Tom informativo. Não use datas, saudações, links ou []. Responda APENAS com o texto do tweet.")
    data_payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.5}}
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=data_payload, timeout=45)
        response.raise_for_status(); data = response.json()
        if data.get("candidates", [{}])[0].get("content", {}).get("parts"):
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e: logger.error(f"Erro na API Gemini: {e}"); return None

def select_trends_from_twitter(driver):
    logger.info(f"Acessando a página de trends: {TWITTER_TRENDS_URL}")
    driver.get(TWITTER_TRENDS_URL)
    trends = []
    try:
        wait = WebDriverWait(driver, 20)
        # Seletor mais robusto para a div que contém as trends
        trends_container = wait.until(EC.visibility_of_element_located((By.XPATH, '//section[@aria-labelledby]')))
        # Seletor para os spans dentro das trends
        elements = trends_container.find_elements(By.XPATH, ".//div[@data-testid='trend']//span")
        
        # Filtro para pegar apenas os nomes das trends (ex: #Python), ignorando "Trending in..." e "1,234 posts"
        trends = list(dict.fromkeys([
            e.text.strip() for e in elements 
            if e.text.strip() and e.text.strip().startswith('#')
        ]))
        
        if trends:
            logger.info(f"Trends encontradas: {len(trends)} -> {trends[:5]}")
        else:
            logger.warning("Nenhuma trend com '#' foi encontrada na página.")
            driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "no_trends_found.png"))
            
    except Exception as e:
        logger.error(f"Erro ao selecionar trends: {e}", exc_info=True)
        driver.save_screenshot(os.path.join(SCREENSHOT_DIR, "error_selecting_trends.png"))
    return trends

def post_tweet_on_twitter(driver, tweet_content):
    driver.get(TWITTER_HOME_URL_FOR_TWEET_BUTTON)
    try:
        wait = WebDriverWait(driver, 30)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@data-testid='SideNav_NewTweet_Button']"))).click()
        tweet_area = wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@data-testid='tweetTextarea_0']")))
        tweet_area.send_keys(tweet_content)
        submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@data-testid='tweetButton']")))
        try: submit_button.click()
        except ElementClickInterceptedException: driver.execute_script("arguments[0].click();", submit_button)
        wait.until(EC.invisibility_of_element_located((By.XPATH, "//div[contains(@data-testid,'tweetTextarea_0')]")))
        return True
    except Exception as e:
        logger.error(f"Erro ao postar tweet: {e}"); return False

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
    global bot_stats
    # Não precisa mais do 'manual_run' flag, a lógica do agendador cuida disso
    logger.info("--- Iniciando ciclo do bot ---")
    driver, chosen_trend, success = None, None, False
    try:
        driver = init_driver(PROFILE_PATH) 
        trends = select_trends_from_twitter(driver)
        if trends:
            chosen_trend = random.choice(trends)
            logger.info(f"Trend selecionada: '{chosen_trend}'")
            tweet_text = get_tweet_content_from_gemini(chosen_trend, load_config().get('custom_prompt', ''))
            if tweet_text: success = post_tweet_on_twitter(driver, tweet_text)
        else: logger.warning("Nenhuma trend foi encontrada.")
    except Exception as e: logger.error(f"Erro geral na tarefa: {e}", exc_info=True)
    finally:
        bot_stats.add_tweet_attempt(success, chosen_trend)
        app_tk.after(0, update_stats_display); app_tk.after(0, update_history_tree)
        if driver: driver.quit()
        logger.info("--- Ciclo do bot finalizado ---")

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
    if not bot_stats.start_time: return
    uptime = str(datetime.now() - bot_stats.start_time).split('.')[0]; rate = bot_stats.get_success_rate()
    stats_text = (f"Tempo Ativo: {uptime}\nTotal: {bot_stats.total_tweets} | Sucesso: {bot_stats.successful_tweets} | Falhas: {bot_stats.failed_tweets}\nTaxa de Sucesso: {rate:.1f}%")
    if bot_stats.last_tweet_time: stats_text += f"\nÚltimo Tweet: {bot_stats.last_tweet_time.strftime('%H:%M:%S')}"
    stats_text_widget.config(state='normal'); stats_text_widget.delete(1.0, tk.END); stats_text_widget.insert(1.0, stats_text); stats_text_widget.config(state='disabled')
    success_progress['value'] = rate; success_label.config(text=f"{rate:.1f}% ({bot_stats.successful_tweets}/{bot_stats.total_tweets})")

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
interval_entry.bind('<FocusOut>', lambda e: apply_interval_change()); interval_entry.bind('<Return>', lambda e: apply_interval_change())
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