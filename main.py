import subprocess
import time
import sys
import os
import csv
import logging
import uvicorn
import threading
from fastapi import FastAPI
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

# === Конфигурация часового пояса ===
MSK_TZ = ZoneInfo("Europe/Moscow")

# === Кастомный обработчик для записи логов в CSV ===
class CSVLoggingHandler(logging.Handler):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        if not os.path.exists(self.filename):
            with open(self.filename, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'level', 'source', 'message'])

    def emit(self, record):
        log_entry = [
            datetime.now(tz=MSK_TZ).strftime('%H:%M.%m.%d'),
            record.levelname,
            record.name if hasattr(record, 'name') else 'main',
            record.getMessage()
        ]
        with open(self.filename, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(log_entry)

# === Настройка логирования ===
def msk_time(*args):
    return datetime.now(tz=MSK_TZ).timetuple()

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    formatter.converter = msk_time

    csv_handler = CSVLoggingHandler("log.csv")
    csv_handler.setFormatter(formatter)
    logger.addHandler(csv_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

setup_logging()

# === Глобальные переменные ===
MAX_RESTART_ATTEMPTS = 3
shutdown_flag = threading.Event()
child_processes = []

# === Запуск скрипта ===
def run_script(script_name, restart_count=0):
    logger = logging.getLogger(script_name)
    try:
        logger.info(f'Запуск скрипта')
        process = subprocess.Popen([sys.executable, script_name])
        child_processes.append(process)
        return process
    except Exception as e:
        logger.error(f'Ошибка при запуске: {e}')
        return None

# === Мониторинг процесса ===
def monitor_process(script_name, process, restart_count=0):
    logger = logging.getLogger(script_name)
    try:
        process.wait()
        if shutdown_flag.is_set():
            logger.info(f"{script_name} завершён пользователем — перезапуск не требуется.")
            return

        if process.returncode != 0:
            logger.warning(f'Процесс завершён с кодом ошибки: {process.returncode}')
            if restart_count < MAX_RESTART_ATTEMPTS:
                logger.info(f'Попытка перезапуска (Попытка {restart_count + 1})')
                new_process = run_script(script_name, restart_count + 1)
                if new_process:
                    monitor_process(script_name, new_process, restart_count + 1)
            else:
                logger.error('Превышено максимальное количество попыток перезапуска')
        else:
            logger.info(f'Процесс завершён успешно с кодом: {process.returncode}')
    except Exception as e:
        logger.error(f'Ошибка при мониторинге: {e}')

# === Основной цикл запуска ===
def main_loop():
    logger = logging.getLogger('main_loop')

    try:
        dump_log_process = run_script("dump-log.py")
        if dump_log_process:
            threading.Thread(target=monitor_process, args=("dump-log.py", dump_log_process)).start()

        logger.info('Ожидание 1 минута перед запуском остальных скриптов...')
        time.sleep(60)

        google_process = None
        yandex_process = None
        tender_process = None

        while not shutdown_flag.is_set():
            if google_process is None or google_process.poll() is not None:
                google_process = run_script("news_google.py")
                if google_process:
                    threading.Thread(target=monitor_process, args=("news_google.py", google_process)).start()

            if yandex_process is None or yandex_process.poll() is not None:
                yandex_process = run_script("news_yandex.py")
                if yandex_process:
                    threading.Thread(target=monitor_process, args=("news_yandex.py", yandex_process)).start()

            if tender_process is None or tender_process.poll() is not None:
                tender_process = run_script("tender_yandex.py")
                if tender_process:
                    threading.Thread(target=monitor_process, args=("tender_yandex.py", tender_process)).start()

            time.sleep(10)

    except KeyboardInterrupt:
        logger.warning("Остановка пользователем (Ctrl+C)")
        shutdown_flag.set()
        for proc in child_processes:
            if proc.poll() is None:
                logger.info(f"Завершаем процесс {proc.pid}")
                proc.terminate()
        logger.info("Все процессы остановлены. Выход.")
        sys.exit(0)

# === FastAPI-сервер ===
app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "ok"}

@app.get("/logs")
def logs():
    return {"message": "Сервис работает."}

def run_server():
    logger = logging.getLogger('server')
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Запуск сервера на порту {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

# === Точка входа ===
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    main_loop()
