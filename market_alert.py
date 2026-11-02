"""Track MCX/COMEX gold prices and email alerts for sharp drops.

Configure data-provider URLs and SMTP credentials in .env. The MCX endpoint is
provider-specific; the COMEX default uses Yahoo Finance's GC=F chart endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sqlite3
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "market_history.db")
HISTORY_WINDOW = max(1, int(os.getenv("HISTORY_WINDOW", "12")))
ALERT_PERCENT_DROP = float(os.getenv("ALERT_PERCENT_DROP", "5.0"))
TIMEOUT_SECONDS = 20


def _find_price(value: Any) -> float | None:
    """Extract a plausible latest price from common market API JSON shapes."""
    if isinstance(value, dict):
        for key in ("regularMarketPrice", "price", "last", "close", "value"):
            candidate = value.get(key)
            if isinstance(candidate, (int, float)) and candidate > 0:
                return float(candidate)
        try:
            result = value["chart"]["result"][0]
            quote_data = result["indicators"]["quote"][0]
            values = quote_data.get("close")
            if values:
                for candidate in reversed(values):
                    if isinstance(candidate, (int, float)) and candidate > 0:
                        return float(candidate)
            meta_price = result.get("meta", {}).get("regularMarketPrice")
            if isinstance(meta_price, (int, float)) and meta_price > 0:
                return float(meta_price)
        except (KeyError, IndexError, TypeError):
            pass
        for child in value.values():
            found = _find_price(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in reversed(value):
            found = _find_price(child)
            if found is not None:
                return found
    elif isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def fetch_price(market: str, url: str, symbol: str) -> float:
    if not url:
        if not symbol:
            raise ValueError(f"Set {market}_PRICE_API_URL or {market}_SYMBOL in .env")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='=^.-')}"

    response = requests.get(
        url,
        headers={"User-Agent": "gold-price-alert/1.0"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    try:
        payload = response.json()
        price = _find_price(payload)
    except (ValueError, json.JSONDecodeError):
        try:
            price = float(response.text.strip())
        except ValueError:
            price = None
    if price is None:
        raise ValueError(f"Could not find a price in the {market} API response")
    return price


def save_and_compare(market: str, price: float) -> tuple[float | None, int]:
    """Store this sample and compare it with the previous rolling samples."""
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS prices ("
            "market TEXT NOT NULL, price REAL NOT NULL, sampled_at TEXT NOT NULL)"
        )
        previous = connection.execute(
            "SELECT price FROM prices WHERE market = ? "
            "ORDER BY rowid DESC LIMIT ?",
            (market, HISTORY_WINDOW),
        ).fetchall()
        connection.execute(
            "INSERT INTO prices (market, price, sampled_at) VALUES (?, ?, ?)",
            (market, price, datetime.now(timezone.utc).isoformat()),
        )
    if not previous:
        return None, 0
    average = sum(row[0] for row in previous) / len(previous)
    if average <= 0:
        return None, len(previous)
    return (price - average) / average * 100, len(previous)


def send_email(subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    recipient = os.getenv("EMAIL_TO", "").strip()
    sender = os.getenv("EMAIL_FROM", "").strip() or os.getenv("SMTP_USER", "").strip()
    if not (host and recipient and sender):
        print("Email is not configured; set SMTP_HOST, EMAIL_TO, and EMAIL_FROM in .env", file=sys.stderr)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    use_ssl = os.getenv("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes")
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(host, port, timeout=TIMEOUT_SECONDS) as smtp:
        if not use_ssl:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)
    print(f"Email sent to {recipient}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test-email",
        action="store_true",
        help="send a test message using the SMTP settings in .env, without fetching prices",
    )
    args = parser.parse_args(argv)

    if args.test_email:
        try:
            sent = send_email(
                "Gold price alert - SMTP test",
                "This is a test email from the gold price alert application.\n"
                "If you received it, SMTP delivery is configured.",
            )
            return 0 if sent else 1
        except (OSError, smtplib.SMTPException, ValueError) as error:
            print(f"SMTP test failed: {error}", file=sys.stderr)
            return 1

    markets = (
        ("MCX", os.getenv("MCX_PRICE_API_URL", "").strip(), os.getenv("MCX_SYMBOL", "").strip()),
        (
            "COMEX",
            os.getenv(
                "COMEX_PRICE_API_URL",
                "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
            ).strip(),
            os.getenv("COMEX_SYMBOL", "GC=F").strip(),
        ),
    )
    reports: list[str] = []
    triggered: list[str] = []
    failures: list[str] = []

    for market, url, symbol in markets:
        if market == "MCX" and not url and not symbol:
            print("Skipping MCX: configure MCX_PRICE_API_URL or MCX_SYMBOL")
            continue
        try:
            price = fetch_price(market, url, symbol)
            change, sample_count = save_and_compare(market, price)
            line = f"{market}: {price:,.2f}"
            if change is not None:
                line += f" (change vs previous {sample_count}-sample average: {change:+.2f}%)"
                if change <= -ALERT_PERCENT_DROP:
                    triggered.append(market)
            else:
                line += " (collecting history; no comparison yet)"
            reports.append(line)
            print(line)
        except (requests.RequestException, ValueError, sqlite3.Error) as error:
            failures.append(f"{market}: {error}")
            print(f"Unable to update {market}: {error}", file=sys.stderr)

    if triggered:
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
        body = (
            "A sharp gold-price drop was detected.\n\n"
            + "\n".join(reports)
            + f"\n\nAlert threshold: {ALERT_PERCENT_DROP:.2f}% drop"
            + f"\nChecked: {timestamp}"
        )
        context = os.getenv("MARKET_CONTEXT", "").strip()
        if context:
            body += "\n\nMarket context:\n" + context
        try:
            send_email(f"Gold price drop alert: {', '.join(triggered)}", body)
        except (OSError, smtplib.SMTPException, ValueError) as error:
            print(f"Unable to send alert email: {error}", file=sys.stderr)
            return 1

    if failures and not reports:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
