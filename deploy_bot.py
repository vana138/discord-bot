import os
import subprocess
import logging
import requests
from dotenv import load_dotenv
from cookies import generate_cookies_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_command(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        logger.info(f"Выполнено: {' '.join(command)}")
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка команды {' '.join(command)}: {e.stderr}")
        return False, e.stderr

def generate_and_upload_cookies():
    try:
        logger.info("Генерация cookies.txt...")
        if not generate_cookies_file():
            logger.error("Не удалось сгенерировать cookies.txt")
            return False

        if not os.path.exists("cookies.txt"):
            logger.error("Файл cookies.txt не создан")
            return False

        commands = [
            ["git", "add", "cookies.txt"],
            ["git", "commit", "-m", "Update cookies.txt"],
            ["git", "push", "origin", "main"]
        ]

        for cmd in commands:
            success, output = run_command(cmd)
            if not success:
                logger.error(f"Ошибка: {output}")
                return False

        logger.info("cookies.txt загружен на GitHub")
        return True

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return False

def trigger_render_deploy():
    try:
        render_api_key = os.getenv("RENDER_API_KEY")
        render_service_id = os.getenv("RENDER_SERVICE_ID")

        if not render_api_key or not render_service_id:
            logger.error("RENDER_API_KEY или RENDER_SERVICE_ID отсутствуют в .env")
            return False

        url = f"https://api.render.com/v1/services/{render_service_id}/deploys"
        headers = {
            "Authorization": f"Bearer {render_api_key}",
            "Content-Type": "application/json"
        }
        response = requests.post(url, headers=headers, json={})
        if response.status_code == 201:
            logger.info("Перезапуск бота на Render начат")
            return True
        else:
            logger.error(f"Ошибка Render API: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Ошибка перезапуска: {e}")
        return False

def main():
    load_dotenv()
    if not generate_and_upload_cookies():
        logger.error("Не удалось обновить cookies")
        return
    if not trigger_render_deploy():
        logger.error("Не удалось перезапустить бота")
        return
    logger.info("Успех! Бот перезапускается на Render.")

if __name__ == "__main__":
    main()