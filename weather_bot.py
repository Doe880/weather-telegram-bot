import os
import sys
from datetime import datetime
from html import escape

import requests


WEATHER_CODES = {
    0: "Ясно",
    1: "Преимущественно ясно",
    2: "Переменная облачность",
    3: "Пасмурно",
    45: "Туман",
    48: "Иней / туман",
    51: "Слабая морось",
    53: "Морось",
    55: "Сильная морось",
    61: "Небольшой дождь",
    63: "Дождь",
    65: "Сильный дождь",
    71: "Небольшой снег",
    73: "Снег",
    75: "Сильный снег",
    80: "Небольшие ливни",
    81: "Ливни",
    82: "Сильные ливни",
    95: "Гроза",
    96: "Гроза с градом",
    99: "Сильная гроза с градом",
}

RU_WEEKDAYS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Не задана переменная окружения: {name}")
    return value


def format_number(value, digits=1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}".replace(".", ",")


def get_weather_forecast():
    city = os.getenv("WEATHER_CITY", "Москва")
    latitude = os.getenv("WEATHER_LAT", "55.7558")
    longitude = os.getenv("WEATHER_LON", "37.6173")
    timezone = os.getenv("WEATHER_TIMEZONE", "Europe/Moscow")

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "forecast_days": 7,
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
            ]
        ),
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    daily = data.get("daily")

    if not daily:
        raise RuntimeError("Open-Meteo не вернул дневной прогноз.")

    return city, daily


def build_message(city: str, daily: dict) -> str:
    dates = daily["time"]
    weather_codes = daily["weather_code"]
    temp_max = daily["temperature_2m_max"]
    temp_min = daily["temperature_2m_min"]
    precipitation_sum = daily["precipitation_sum"]
    precipitation_probability = daily["precipitation_probability_max"]

    lines = [
        f"🌤 <b>Прогноз погоды на неделю: {escape(city)}</b>",
        "",
    ]

    for i, date_str in enumerate(dates):
        date_obj = datetime.fromisoformat(date_str)
        weekday = RU_WEEKDAYS[date_obj.weekday()]
        date_formatted = date_obj.strftime("%d.%m")

        code = weather_codes[i]
        description = WEATHER_CODES.get(code, "Погодные условия")

        max_temp = round(temp_max[i])
        min_temp = round(temp_min[i])
        rain_mm = format_number(precipitation_sum[i])
        rain_prob = precipitation_probability[i]

        rain_prob_text = "—" if rain_prob is None else f"{rain_prob}%"

        lines.append(
            f"<b>{weekday}, {date_formatted}</b>: "
            f"{description}, "
            f"{min_temp}…{max_temp}°C, "
            f"осадки: {rain_mm} мм, "
            f"вероятность: {rain_prob_text}"
        )

    lines.append("")
    lines.append("☔️ Осадки указаны в миллиметрах за сутки.")

    return "\n".join(lines)


def send_telegram_message(text: str):
    token = get_required_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_required_env("TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    response = requests.post(url, json=payload, timeout=30)

    if not response.ok:
        raise RuntimeError(f"Ошибка Telegram API: {response.status_code} {response.text}")

    return response.json()


def main():
    try:
        city, daily = get_weather_forecast()
        message = build_message(city, daily)
        send_telegram_message(message)
        print("Прогноз успешно отправлен.")
    except Exception as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()