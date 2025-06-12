import os
import subprocess
import logging
import requests
from dotenv import load_dotenv
from cookies import generate_cookies_file

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_command(command):
    """
    Выполняет команду в терминале и возвращает результат.
    """
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        logger.info(f"Команда выполнена: {' '.join(command)}")
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при выполнении команды {' '.join(command)}: {e.stderr}")
        return False, e.stderr

def generate_and_upload_cookies():
    """
    Генерирует cookies.txt и загружает его в репозиторий на GitHub.
    """
    try:
        # Генерация cookies.txt
        logger.info("Генерация cookies.txt...")
        if not generate_cookies_file(browser="edge", output_file="cookies.txt"):
            logger.error("Не удалось сгенерировать cookies.txt")
            return False

        # Проверка, существует ли cookies.txt
        if not os.path.exists("cookies.txt"):
            logger.error("Файл cookies.txt не был создан")
            return False

        # Git команды для коммита и пуша
        commands = [
            ["git", "add", "cookies.txt"],
            ["git", "commit", "-m", "Автоматическое обновление cookies.txt"],
            ["git", "push", "origin", "main"]
        ]

        for cmd in commands:
            success, output = run_command(cmd)
            if not success:
                logger.error(f"Ошибка при выполнении команды: {output}")
                return False

        logger.info("cookies.txt успешно загружен в репозиторий")
        return True

    except Exception as e:
        logger.error(f"Ошибка при генерации или загрузке cookies: {e}")
        return False

def trigger_render_deploy():
    """
    Отправляет запрос к Render.com API для перезапуска сервиса.
    """
    try:
        render_api_key = os.getenv("RENDER_API_KEY")
        render_service_id = os.getenv("RENDER_SERVICE_ID")

        if not render_api_key or not render_service_id:
            logger.error("RENDER_API_KEY или RENDER_SERVICE_ID не найдены в .env")
            return False

        url = f"https://api.render.com/v1/services/{render_service_id}/deploys"
        headers = {
            "Authorization": f"Bearer {render_api_key}",
            "Content-Type": "application/json"
        }
        data = {}

        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 201:
            logger.info("Перезапуск сервиса на Render.com инициирован")
            return True
        else:
            logger.error(f"Ошибка при запросе к Render API: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Ошибка при перезапуске сервиса: {e}")
        return False

def main():
    """
    Основная функция для генерации cookies, загрузки на GitHub и перезапуска бота.
    """
    # Загрузка переменных окружения
    load_dotenv()

    # Генерация и загрузка cookies
    if not generate_and_upload_cookies():
        logger.error("Не удалось выполнить генерацию или загрузку cookies.txt")
        return

    # Перезапуск сервиса на Render.com
    if not trigger_render_deploy():
        logger.error("Не удалось инициировать перезапуск сервиса на Render.com")
        return

    logger.info("Все шаги выполнены успешно! Бот перезапускается на Render.com.")

if __name__ == "__main__":
    main()