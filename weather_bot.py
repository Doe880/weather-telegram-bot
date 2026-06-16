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

DAY_PARTS = [
    ("🌅 Утро", 8),
    ("☀️ День", 14),
    ("🌙 Вечер", 20),
]


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
    city = os.getenv("WEATHER_CITY", "Талдом, Московская область")
    latitude = os.getenv("WEATHER_LAT", "56.7333")
    longitude = os.getenv("WEATHER_LON", "37.5333")
    timezone = os.getenv("WEATHER_TIMEZONE", "Europe/Moscow")

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "forecast_days": 7,
        "hourly": ",".join(
            [
                "temperature_2m",
                "weather_code",
                "precipitation",
                "precipitation_probability",
                "wind_speed_10m",
            ]
        ),
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    hourly = data.get("hourly")

    if not hourly:
        raise RuntimeError("Open-Meteo не вернул почасовой прогноз.")

    return city, hourly


def group_hourly_by_date(hourly: dict) -> dict:
    grouped = {}

    times = hourly["time"]
    temperatures = hourly["temperature_2m"]
    weather_codes = hourly["weather_code"]
    precipitations = hourly["precipitation"]
    precipitation_probabilities = hourly["precipitation_probability"]
    wind_speeds = hourly["wind_speed_10m"]

    for i, time_str in enumerate(times):
        dt = datetime.fromisoformat(time_str)
        date_key = dt.date().isoformat()
        hour = dt.hour

        if date_key not in grouped:
            grouped[date_key] = {}

        grouped[date_key][hour] = {
            "datetime": dt,
            "temperature": temperatures[i],
            "weather_code": weather_codes[i],
            "precipitation": precipitations[i],
            "precipitation_probability": precipitation_probabilities[i],
            "wind_speed": wind_speeds[i],
        }

    return grouped


def build_message(city: str, hourly: dict) -> str:
    grouped = group_hourly_by_date(hourly)

    lines = [
        f"🌤 <b>Прогноз погоды на неделю: {escape(city)}</b>",
        "",
        "Погода по периодам: утро, день, вечер.",
        "",
    ]

    for date_key in list(grouped.keys())[:7]:
        day_data = grouped[date_key]

        first_hour = next(iter(day_data.values()))
        date_obj = first_hour["datetime"]

        weekday = RU_WEEKDAYS[date_obj.weekday()]
        date_formatted = date_obj.strftime("%d.%m")

        lines.append(f"<b>{weekday}, {date_formatted}</b>")

        for part_name, hour in DAY_PARTS:
            item = day_data.get(hour)

            if not item:
                lines.append(f"{part_name} {hour:02d}:00: данных нет")
                continue

            temperature = round(item["temperature"])
            weather_code = item["weather_code"]
            description = WEATHER_CODES.get(weather_code, "Погодные условия")

            precipitation = format_number(item["precipitation"])
            probability = item["precipitation_probability"]
            probability_text = "—" if probability is None else f"{probability}%"

            wind_speed = format_number(item["wind_speed"])

            lines.append(
                f"{part_name} {hour:02d}:00: "
                f"{temperature}°C, "
                f"{description}, "
                f"осадки {precipitation} мм, "
                f"вероятность {probability_text}, "
                f"ветер {wind_speed} км/ч"
            )

        lines.append("")

    lines.append("☔️ Осадки указаны в миллиметрах за выбранный час.")
    lines.append("🌬 Ветер указан в км/ч.")

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
        city, hourly = get_weather_forecast()
        message = build_message(city, hourly)
        send_telegram_message(message)
        print("Прогноз успешно отправлен.")
    except Exception as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()