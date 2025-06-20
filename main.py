import subprocess
import time
import logging
import sys
import os
from fastapi import FastAPI
import uvicorn
import threading

# === Твой оригинальный код ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
MAX_RESTART_ATTEMPTS = 3

def run_script(script_name, restart_count=0):
    try:
        logging.info(f'Запуск скрипта: {script_name}')
        process = subprocess.Popen(["python", script_name])
        return process
    except Exception as e:
        logging.error(f'Ошибка при запуске {script_name}: {e}')
        return None

def monitor_process(script_name, process, restart_count=0):
    try:
        process.wait()
        if process.returncode != 0:
            logging.warning(f'Скрипт {script_name} завершился с кодом ошибки: {process.returncode}')
            if restart_count < MAX_RESTART_ATTEMPTS:
                logging.info(f'Попытка перезапуска {script_name} (Попытка {restart_count + 1})')
                new_process = run_script(script_name, restart_count + 1)
                if new_process:
                    monitor_process(script_name, new_process, restart_count + 1)
            else:
                logging.error(f'Превышено максимальное количество попыток перезапуска для {script_name}')
        else:
            logging.info(f'Скрипт {script_name} завершился успешно с кодом: {process.returncode}')
    except Exception as e:
        logging.error(f'Ошибка при мониторинге {script_name}: {e}')

def main_loop():
    while True:
        google_process = run_script("news_from_google.py")
        yandex_process = run_script("news_from_yandex.py")

        if google_process:
            monitor_process("news_from_google.py", google_process)
        if yandex_process:
            monitor_process("news_from_yandex.py", yandex_process)

        logging.info('Ожидание перед следующей итерацией...')
        time.sleep(60)  # Пауза между циклами

# === Новый FastAPI сервер для работы с Render ===
app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "ok"}

@app.get("/logs")
def logs():
    return {"message": "Сервис работает. Подробности в логах Render."}

def run_server():
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# === Запуск всего вместе ===
if __name__ == "__main__":
    # Запускаем веб-сервер в отдельном потоке
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    # Основной цикл запуска скриптов
    main_loop()

