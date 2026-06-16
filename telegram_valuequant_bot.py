import argparse
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from balance_analyzer import analizar_balance
from cashflow_analyzer import analizar_flujo_efectivo
from downloader import obtener_estados_financieros
from income_analyzer import analizar_cuenta_resultados
from modulos.utils import calcular_score_buffett


BOT_NAME = "ValueQuant Terminal"
BOT_USERNAME = "ValueQuant_Bot"
DEFAULT_BOT_TOKEN = "8214200710:AAHLBIJU9NImuntjldfma7DUUTMfXbcNlCU"
DATA_DIR = Path("data")
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
STATE_FILE = DATA_DIR / "telegram_alert_state.json"
SUBSCRIBERS_FILE = DATA_DIR / "telegram_subscribers.json"
RANKING_FILE = Path("ranking_mercado.csv")
TZ = ZoneInfo("Europe/Paris")


def bot_token():
    return os.getenv("TELEGRAM_BOT_TOKEN", DEFAULT_BOT_TOKEN).strip()


class TelegramAPI:
    def __init__(self, token=None):
        self.token = token or bot_token()
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def request(self, method, payload=None, timeout=20):
        url = f"{self.base_url}/{method}"
        response = requests.post(url, json=payload or {}, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(data)
        return data.get("result")

    def send_message(self, chat_id, text, disable_preview=True):
        chunks = split_message(text)
        for chunk in chunks:
            self.request(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": disable_preview,
                },
            )

    def get_updates(self, offset=None, timeout=25):
        payload = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        return self.request("getUpdates", payload=payload, timeout=timeout + 5)

    def configure_profile(self):
        self.request(
            "setMyCommands",
            {
                "commands": [
                    {"command": "start", "description": "Suscribirme a alertas ValueQuant"},
                    {"command": "help", "description": "Ver comandos disponibles"},
                    {"command": "watchlist", "description": "Revisar precios objetivo"},
                    {"command": "briefing", "description": "Morning briefing de mercado"},
                    {"command": "timing", "description": "Analizar timing: /timing AAPL MSFT SPY"},
                    {"command": "insiders", "description": "Rastrear insiders: /insiders META"},
                    {"command": "podio", "description": "Top semanal del ranking Buffett"},
                    {"command": "scan", "description": "Ejecutar escaneo completo de alertas"},
                ]
            },
        )
        self.request(
            "setMyDescription",
            {
                "description": (
                    "ValueQuant Terminal vigila watchlist, valoración, señales técnicas, "
                    "insiders y reportes automáticos de mercado."
                )
            },
        )
        self.request(
            "setMyShortDescription",
            {"short_description": "Alertas de inversión value, timing cuantitativo y smart money."},
        )


def split_message(text, limit=3900):
    if len(text) <= limit:
        return [text]
    chunks = []
    current = []
    size = 0
    for line in text.splitlines():
        line_size = len(line) + 1
        if size + line_size > limit and current:
            chunks.append("\n".join(current))
            current = [line]
            size = line_size
        else:
            current.append(line)
            size += line_size
    if current:
        chunks.append("\n".join(current))
    return chunks


def load_json(path, default):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def load_watchlist():
    raw = load_json(WATCHLIST_FILE, {})
    watchlist = {}
    for ticker, config in raw.items():
        if isinstance(config, dict):
            watchlist[ticker.upper()] = config
        else:
            watchlist[ticker.upper()] = {"target": float(config or 0)}
    return watchlist


def load_subscribers():
    env_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    subscribers = load_json(SUBSCRIBERS_FILE, [])
    if env_chat_id and env_chat_id not in subscribers:
        subscribers.append(env_chat_id)
    return [str(chat_id) for chat_id in subscribers]


def add_subscriber(chat_id):
    subscribers = load_subscribers()
    chat_id = str(chat_id)
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_json(SUBSCRIBERS_FILE, subscribers)
    return subscribers


def price_snapshot(ticker):
    tk = yf.Ticker(ticker)
    hist = tk.history(period="5d", interval="1d")
    if hist.empty:
        price = float(tk.fast_info.last_price)
        previous = float(tk.fast_info.previous_close)
    elif len(hist) >= 2:
        price = float(hist["Close"].iloc[-1])
        previous = float(hist["Close"].iloc[-2])
    else:
        price = float(hist["Close"].iloc[-1])
        previous = price
    change = ((price - previous) / previous) * 100 if previous else 0
    return price, change


def scan_watchlist_value():
    watchlist = load_watchlist()
    if not watchlist:
        return ["📋 Watchlist vacía. Añade tickers desde Streamlit para activar alertas."]

    alerts = []
    state = load_json(STATE_FILE, {})
    fired_targets = state.setdefault("fair_value_crosses", {})

    for ticker, config in watchlist.items():
        target = float(config.get("target") or 0)
        if target <= 0:
            continue
        try:
            price, change = price_snapshot(ticker)
            crossed = price <= target
            previous_state = fired_targets.get(ticker)
            if crossed and previous_state != "crossed":
                margin = ((target - price) / target) * 100
                alerts.append(
                    f"🟢 <b>Fair Value activado</b>\n"
                    f"${ticker} cotiza a <b>${price:.2f}</b> ({change:+.2f}%).\n"
                    f"Ha cruzado tu precio objetivo de <b>${target:.2f}</b>. "
                    f"Margen adicional: <b>{margin:.1f}%</b>."
                )
                fired_targets[ticker] = "crossed"
            elif not crossed:
                fired_targets[ticker] = "above"
        except Exception as exc:
            alerts.append(f"⚠️ No pude leer precio de ${ticker}: {exc}")

    save_json(STATE_FILE, state)
    return alerts or ["📋 Watchlist revisada: ningún precio objetivo cruzado ahora mismo."]


def get_last(df, col):
    if df is not None and col in df.columns:
        serie = df[col].dropna()
        return serie.iloc[-1] if not serie.empty else None
    return None


def scan_fundamental_deterioration(max_tickers=5):
    watchlist = list(load_watchlist().keys())[:max_tickers]
    if not watchlist:
        return []

    alerts = []
    for ticker in watchlist:
        try:
            is_df, bs_df, cf_df = obtener_estados_financieros(ticker, años=5, usar_cache=True)
            if is_df is None or bs_df is None or cf_df is None:
                continue
            res_is = analizar_cuenta_resultados(is_df, cf_df)
            res_bs = analizar_balance(bs_df, is_df)
            res_cf = analizar_flujo_efectivo(cf_df, is_df)
            score = calcular_score_buffett(res_is["ratios"], res_bs["ratios"], res_cf["ratios"])
            debt_cap = get_last(res_bs["ratios"], "Deuda / Capital")
            roic = get_last(res_bs["ratios"], "ROIC %")
            fcf = get_last(res_cf["ratios"], "Free Cash Flow (B USD)")

            if debt_cap is not None and debt_cap > 1.2:
                alerts.append(
                    f"🚨 <b>Deterioro fundamental</b>\n"
                    f"${ticker}: Deuda/Capital en <b>{debt_cap:.2f}x</b>. "
                    f"Buffett Score: <b>{score}/100</b>."
                )
            if roic is not None and roic < 7:
                alerts.append(
                    f"📉 <b>ROIC bajo</b>\n"
                    f"${ticker}: ROIC actual <b>{roic:.1f}%</b>. Puede estar destruyendo capital."
                )
            if fcf is not None and fcf < 0:
                alerts.append(
                    f"🔥 <b>Free Cash Flow negativo</b>\n"
                    f"${ticker}: FCF <b>${fcf:.2f}B</b>. Vigilar dilución/deuda."
                )
        except Exception:
            continue
    return alerts


def upcoming_earnings_alerts():
    watchlist = load_watchlist()
    tomorrow = datetime.now(TZ).date() + timedelta(days=1)
    names = []
    for ticker in watchlist:
        try:
            cal = yf.Ticker(ticker).calendar
            if isinstance(cal, dict):
                raw_date = cal.get("Earnings Date")
                if isinstance(raw_date, list):
                    raw_date = raw_date[0]
            else:
                raw_date = None
            if raw_date is None:
                continue
            earnings_date = pd.to_datetime(raw_date).date()
            if earnings_date == tomorrow:
                names.append(ticker)
        except Exception:
            continue
    if names:
        return [f"🗓️ <b>Earnings mañana</b>\nPresentan resultados: {', '.join(f'${t}' for t in names)}."]
    return []


def technical_frame(ticker, period="1y"):
    df = yf.Ticker(ticker).history(period=period, interval="1d")
    if df.empty or len(df) < 220:
        return None
    df = df.dropna().copy()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["Close"].ewm(span=200, adjust=False).mean()
    df["sma20"] = df["Close"].rolling(20).mean()
    df["std20"] = df["Close"].rolling(20).std()
    df["bb_upper"] = df["sma20"] + 2 * df["std20"]
    df["bb_lower"] = df["sma20"] - 2 * df["std20"]

    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr20 = tr.rolling(20).mean()
    df["kc_upper"] = df["sma20"] + 1.5 * atr20
    df["kc_lower"] = df["sma20"] - 1.5 * atr20
    df["volume20"] = df["Volume"].rolling(20).mean()
    df["zscore"] = (df["Close"] - df["sma20"]) / df["std20"]

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi_min = rsi.rolling(14).min()
    rsi_max = rsi.rolling(14).max()
    df["stoch_rsi"] = (rsi - rsi_min) / (rsi_max - rsi_min)
    df["squeeze_on"] = (df["bb_upper"] < df["kc_upper"]) & (df["bb_lower"] > df["kc_lower"])
    return df


def scan_timing(tickers):
    alerts = []
    for ticker in tickers:
        try:
            df = technical_frame(ticker)
            if df is None:
                continue
            last = df.iloc[-1]
            prev = df.iloc[-2]

            if prev["ema50"] <= prev["ema200"] and last["ema50"] > last["ema200"]:
                alerts.append(
                    f"🌊 <b>Golden Cross</b>\n"
                    f"${ticker}: EMA 50 acaba de cruzar por encima de EMA 200."
                )

            squeeze_fired = bool(prev["squeeze_on"]) and not bool(last["squeeze_on"])
            institutional_volume = last["Volume"] > 1.8 * last["volume20"]
            breakout = last["Close"] > last["bb_upper"]
            if squeeze_fired and institutional_volume and breakout:
                alerts.append(
                    f"🔥 <b>ALERTA DE BREAKOUT</b>\n"
                    f"${ticker}: sale de compresión Bollinger/Keltner con volumen "
                    f"<b>{last['Volume'] / last['volume20']:.1f}x</b> sobre la media."
                )

            if last["zscore"] <= -2.5 and last["stoch_rsi"] <= 0.05:
                alerts.append(
                    f"🩸 <b>Pánico extremo</b>\n"
                    f"${ticker}: Z-Score <b>{last['zscore']:.2f}</b> y StochRSI en "
                    f"<b>{last['stoch_rsi']:.2f}</b>. Sobreventa máxima."
                )
        except Exception as exc:
            alerts.append(f"⚠️ Error técnico en ${ticker}: {exc}")
    return alerts or ["⚡ Timing revisado: sin señales críticas en los tickers analizados."]


def scan_insiders(tickers, min_value=1_000_000):
    alerts = []
    for ticker in tickers:
        try:
            transactions = yf.Ticker(ticker).insider_transactions
            if transactions is None or transactions.empty:
                continue
            for _, row in transactions.head(12).iterrows():
                action = str(row.get("Transaction", "")).lower()
                value = row.get("Value", 0) or 0
                insider = row.get("Insider", "Directivo")
                if "purchase" in action or "buy" in action or action.strip() == "p":
                    if float(value) >= min_value:
                        alerts.append(
                            f"👔 <b>Compra insider inusual</b>\n"
                            f"${ticker}: {insider} compró aprox. <b>${float(value):,.0f}</b>."
                        )
        except Exception:
            continue
    return alerts or ["🕵️ Insiders revisados: sin compras inusuales detectadas."]


def put_call_alert():
    try:
        hist = yf.Ticker("^CPC").history(period="5d")
        if hist.empty:
            return []
        ratio = float(hist["Close"].iloc[-1])
        if ratio >= 1.5:
            return [
                f"⚠️ <b>Alerta de miedo</b>\n"
                f"Put/Call Ratio en <b>{ratio:.2f}</b>. El mercado se está cubriendo con fuerza."
            ]
    except Exception:
        return []
    return []


def sector_rotation_summary():
    etfs = {
        "Tecnología": "XLK",
        "Salud": "XLV",
        "Finanzas": "XLF",
        "Consumo Discrecional": "XLY",
        "Consumo Básico": "XLP",
        "Energía": "XLE",
        "Industriales": "XLI",
        "Materiales": "XLB",
        "Utilities": "XLU",
        "Comunicaciones": "XLC",
    }
    rows = []
    for sector, ticker in etfs.items():
        try:
            hist = yf.Ticker(ticker).history(period="7d")
            if len(hist) >= 2:
                perf = ((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2]) * 100
                rows.append((sector, perf))
        except Exception:
            continue
    if not rows:
        return "Rotación sectorial no disponible."
    rows.sort(key=lambda item: item[1], reverse=True)
    leader, laggard = rows[0], rows[-1]
    return (
        f"Lidera <b>{leader[0]}</b> ({leader[1]:+.2f}%). "
        f"Rezaga <b>{laggard[0]}</b> ({laggard[1]:+.2f}%)."
    )


def morning_briefing():
    symbols = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "VIX": "^VIX", "Oro": "GC=F", "Petróleo": "CL=F"}
    lines = ["☕ <b>Morning Briefing ValueQuant</b>", f"<i>{datetime.now(TZ):%d/%m/%Y %H:%M}</i>", ""]
    for name, ticker in symbols.items():
        try:
            price, change = price_snapshot(ticker)
            lines.append(f"• {name}: <b>{price:.2f}</b> ({change:+.2f}%)")
        except Exception:
            pass
    lines.append("")
    lines.append(f"• Sectores: {sector_rotation_summary()}")
    lines.extend(upcoming_earnings_alerts())
    return "\n".join(lines)


def weekly_podium():
    if not RANKING_FILE.exists():
        return (
            "🏆 <b>Podio Semanal</b>\n"
            "No existe ranking_mercado.csv todavía. Ejecuta el screener desde la terminal "
            "o lanza screener.py para generar el ranking."
        )
    df = pd.read_csv(RANKING_FILE)
    if df.empty:
        return "🏆 Podio Semanal: ranking_mercado.csv está vacío."
    top = df.head(3)
    lines = ["🏆 <b>Podio Semanal ValueQuant</b>"]
    for idx, (_, row) in enumerate(top.iterrows(), start=1):
        ticker = row.get("Ticker", "N/A")
        score = row.get("Puntuacion Greenblatt", row.get("Buffett Score", "N/D"))
        lines.append(f"{idx}. <b>${ticker}</b> · score ranking: {score}")
    return "\n".join(lines)


def default_scan_tickers():
    tickers = list(load_watchlist().keys())
    return tickers or ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]


def run_scan():
    tickers = default_scan_tickers()
    alerts = []
    alerts.extend(scan_watchlist_value())
    alerts.extend(upcoming_earnings_alerts())
    alerts.extend(scan_timing(tickers[:12]))
    alerts.extend(scan_insiders(tickers[:8]))
    alerts.extend(put_call_alert())
    alerts.extend(scan_fundamental_deterioration(max_tickers=4))
    return "\n\n".join(alerts)


def dispatch_to_subscribers(message):
    api = TelegramAPI()
    subscribers = load_subscribers()
    if not subscribers:
        print("No hay suscriptores. Abre Telegram y envía /start al bot.")
        return
    for chat_id in subscribers:
        api.send_message(chat_id, message)


def help_text():
    return (
        f"<b>{BOT_NAME}</b>\n"
        "Comandos disponibles:\n"
        "• /watchlist - revisa precios objetivo\n"
        "• /briefing - resumen de mercado\n"
        "• /timing AAPL MSFT SPY - señales técnicas\n"
        "• /insiders META - compras de directivos\n"
        "• /podio - ranking semanal\n"
        "• /scan - escaneo completo\n\n"
        "Para recibir alertas automáticas, deja este script ejecutándose con --poll."
    )


def handle_command(api, chat_id, text):
    parts = text.strip().split()
    command = parts[0].split("@")[0].lower()
    args = [arg.upper().strip("$") for arg in parts[1:]]

    if command == "/start":
        add_subscriber(chat_id)
        api.send_message(chat_id, f"✅ Suscripción activada en <b>{BOT_NAME}</b>.\n\n{help_text()}")
    elif command == "/help":
        api.send_message(chat_id, help_text())
    elif command == "/watchlist":
        api.send_message(chat_id, "\n\n".join(scan_watchlist_value() + upcoming_earnings_alerts()))
    elif command == "/briefing":
        api.send_message(chat_id, morning_briefing())
    elif command == "/timing":
        api.send_message(chat_id, "\n\n".join(scan_timing(args or default_scan_tickers())))
    elif command == "/insiders":
        api.send_message(chat_id, "\n\n".join(scan_insiders(args or default_scan_tickers())))
    elif command == "/podio":
        api.send_message(chat_id, weekly_podium())
    elif command == "/scan":
        api.send_message(chat_id, run_scan())
    else:
        api.send_message(chat_id, help_text())


def poll_loop():
    api = TelegramAPI()
    api.configure_profile()
    print(f"{BOT_NAME} (@{BOT_USERNAME}) escuchando Telegram...")
    offset = None
    state = load_json(STATE_FILE, {})

    while True:
        try:
            for update in api.get_updates(offset=offset):
                offset = update["update_id"] + 1
                message = update.get("message") or update.get("edited_message") or {}
                text = message.get("text", "")
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                if chat_id and text.startswith("/"):
                    handle_command(api, chat_id, text)

            now = datetime.now(TZ)
            today = now.strftime("%Y-%m-%d")
            weekday_key = now.strftime("%G-W%V")

            if now.hour == 8 and state.get("last_morning_briefing") != today:
                dispatch_to_subscribers(morning_briefing())
                state["last_morning_briefing"] = today
                save_json(STATE_FILE, state)

            if now.weekday() == 4 and now.hour == 22 and state.get("last_weekly_podium") != weekday_key:
                dispatch_to_subscribers(weekly_podium())
                state["last_weekly_podium"] = weekday_key
                save_json(STATE_FILE, state)

            if now.minute in {0, 30} and state.get("last_half_hour_scan") != f"{today}-{now.hour}-{now.minute}":
                dispatch_to_subscribers(run_scan())
                state["last_half_hour_scan"] = f"{today}-{now.hour}-{now.minute}"
                save_json(STATE_FILE, state)
        except KeyboardInterrupt:
            print("Bot detenido.")
            return
        except Exception as exc:
            print(f"Error en polling: {exc}")
            time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description=f"{BOT_NAME} Telegram bot")
    parser.add_argument("--configure", action="store_true", help="Configura comandos/descripcion del bot")
    parser.add_argument("--poll", action="store_true", help="Escucha comandos y envia alertas programadas")
    parser.add_argument("--once", choices=["briefing", "watchlist", "scan", "podio"], help="Envia un reporte a suscriptores")
    args = parser.parse_args()

    if args.configure:
        TelegramAPI().configure_profile()
        print("Perfil y comandos de Telegram configurados.")
    elif args.poll:
        poll_loop()
    elif args.once == "briefing":
        dispatch_to_subscribers(morning_briefing())
    elif args.once == "watchlist":
        dispatch_to_subscribers("\n\n".join(scan_watchlist_value() + upcoming_earnings_alerts()))
    elif args.once == "scan":
        dispatch_to_subscribers(run_scan())
    elif args.once == "podio":
        dispatch_to_subscribers(weekly_podium())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
