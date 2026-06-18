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
    56: "Слабая ледяная морось",
    57: "Сильная ледяная морось",
    61: "Небольшой дождь",
    63: "Дождь",
    65: "Сильный дождь",
    66: "Слабый ледяной дождь",
    67: "Сильный ледяной дождь",
    71: "Небольшой снег",
    73: "Снег",
    75: "Сильный снег",
    77: "Снежные зёрна",
    80: "Небольшие ливни",
    81: "Ливни",
    82: "Сильные ливни",
    85: "Небольшой снегопад",
    86: "Сильный снегопад",
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

MODEL_DISPLAY_NAMES = {
    "best_match": "Open-Meteo Best Match",
    "ecmwf_ifs025": "ECMWF IFS 0.25°",
    "gfs_seamless": "GFS Seamless",
    "icon_seamless": "ICON Seamless",
    "ukmo_seamless": "UKMO Seamless",
}


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Не задана переменная окружения: {name}")
    return value


def format_number(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}".replace(".", ",")


def get_model_display_name(model: str) -> str:
    model = (model or "best_match").strip()
    return MODEL_DISPLAY_NAMES.get(model, model)


def should_send_model_to_api(model: str) -> bool:
    model = (model or "").strip().lower()
    return model not in ("", "auto", "best_match")


def get_hourly_values(hourly: dict, variable_name: str, model: str, required: bool = True):
    """
    Open-Meteo обычно возвращает поля без суффикса:
    temperature_2m, precipitation, weather_code.

    Но при выборе отдельных моделей иногда поля могут быть с суффиксом модели.
    Поэтому функция делает поиск более устойчивым.
    """
    if variable_name in hourly:
        return hourly[variable_name]

    possible_keys = []

    if model:
        possible_keys.append(f"{variable_name}_{model}")

    for key in hourly.keys():
        if key.startswith(f"{variable_name}_"):
            possible_keys.append(key)

    for key in possible_keys:
        if key in hourly:
            return hourly[key]

    if required:
        available_keys = ", ".join(hourly.keys())
        raise RuntimeError(
            f"В ответе Open-Meteo нет переменной '{variable_name}'. "
            f"Доступные поля: {available_keys}"
        )

    time_values = hourly.get("time", [])
    return [None] * len(time_values)


def get_weather_forecast():
    city = os.getenv("WEATHER_CITY", "Талдом, Московская область")
    latitude = os.getenv("WEATHER_LAT", "56.7333")
    longitude = os.getenv("WEATHER_LON", "37.5333")
    timezone = os.getenv("WEATHER_TIMEZONE", "Europe/Moscow")

    # Можно указать в weekly_weather.yml:
    # WEATHER_MODEL: "ecmwf_ifs025"
    #
    # Если WEATHER_MODEL не задан, будет использоваться стандартный Open-Meteo Best Match.
    model = os.getenv("WEATHER_MODEL", "best_match").strip()

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

    if should_send_model_to_api(model):
        params["models"] = model

    response = requests.get(url, params=params, timeout=30)

    if not response.ok:
        raise RuntimeError(
            f"Ошибка Open-Meteo API: {response.status_code} {response.text}"
        )

    data = response.json()
    hourly = data.get("hourly")

    if not hourly:
        raise RuntimeError("Open-Meteo не вернул почасовой прогноз.")

    return city, hourly, model


def group_hourly_by_date(hourly: dict, model: str) -> dict:
    grouped = {}

    times = hourly["time"]
    temperatures = get_hourly_values(hourly, "temperature_2m", model)
    weather_codes = get_hourly_values(hourly, "weather_code", model)
    precipitations = get_hourly_values(hourly, "precipitation", model)
    precipitation_probabilities = get_hourly_values(
        hourly,
        "precipitation_probability",
        model,
        required=False,
    )
    wind_speeds = get_hourly_values(hourly, "wind_speed_10m", model)

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


def build_message(city: str, hourly: dict, model: str) -> str:
    grouped = group_hourly_by_date(hourly, model)
    model_display_name = get_model_display_name(model)

    lines = [
        f"🌤 <b>Прогноз погоды на неделю: {escape(city)}</b>",
        f"📊 Модель прогноза: <b>{escape(model_display_name)}</b>",
        "",
        "Погода по периодам: утро, день, вечер.",
        "",
    ]

    for date_key in sorted(grouped.keys())[:7]:
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

            temperature = item["temperature"]
            weather_code = item["weather_code"]
            precipitation = item["precipitation"]
            probability = item["precipitation_probability"]
            wind_speed = item["wind_speed"]

            temperature_text = "—" if temperature is None else f"{round(temperature)}°C"
            description = WEATHER_CODES.get(weather_code, "Погодные условия")

            precipitation_text = format_number(precipitation)
            probability_text = "—" if probability is None else f"{round(probability)}%"
            wind_speed_text = format_number(wind_speed)

            lines.append(
                f"{part_name} {hour:02d}:00: "
                f"{temperature_text}, "
                f"{description}, "
                f"осадки {precipitation_text} мм, "
                f"вероятность {probability_text}, "
                f"ветер {wind_speed_text} км/ч"
            )

        lines.append("")

    lines.append("☔️ Осадки указаны в миллиметрах за выбранный час.")
    lines.append("🌬 Ветер указан в км/ч.")

    return "\n".join(lines)


def split_message(text: str, max_length: int = 3900) -> list[str]:
    """
    Telegram ограничивает длину сообщения.
    Для нашего прогноза обычно хватает одного сообщения,
    но оставим безопасное разделение на части.
    """
    if len(text) <= max_length:
        return [text]

    parts = []
    current_part = ""

    for line in text.split("\n"):
        if len(current_part) + len(line) + 1 > max_length:
            parts.append(current_part)
            current_part = line
        else:
            current_part += "\n" + line if current_part else line

    if current_part:
        parts.append(current_part)

    return parts


def send_telegram_message(text: str):
    token = get_required_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_required_env("TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for message_part in split_message(text):
        payload = {
            "chat_id": chat_id,
            "text": message_part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        response = requests.post(url, json=payload, timeout=30)

        if not response.ok:
            raise RuntimeError(
                f"Ошибка Telegram API: {response.status_code} {response.text}"
            )


def main():
    try:
        city, hourly, model = get_weather_forecast()
        message = build_message(city, hourly, model)
        send_telegram_message(message)
        print("Прогноз успешно отправлен.")
    except Exception as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()