# Gold Price Comparison Email Alerts

A small Python monitor that records MCX India and COMEX gold prices, compares each new sample with its recent history, and emails an alert when a market drops by the configured threshold. WhatsApp/Twilio notifications have been replaced with SMTP email.

## What it does

- Fetches prices from configurable market-data endpoints (or Yahoo Finance symbols).
- Stores price samples in a local SQLite database.
- Compares each new sample with the previous rolling average.
- Sends an email when a price falls by at least `ALERT_PERCENT_DROP`.
- Can run on a schedule using cron.

## Setup

1. Install Python 3.10 or later and create an environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure credentials and data sources:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, and `EMAIL_TO`. Use an app password if your email provider requires one. Set `MCX_PRICE_API_URL` to a provider that returns the current MCX gold price, or set `MCX_SYMBOL` if using Yahoo Finance. COMEX defaults to the Yahoo Finance `GC=F` chart endpoint.

3. Run a check:

   ```bash
   python3 market_alert.py
   ```

Email is sent only after enough price history exists to detect a drop. Before email settings are configured, alert details are printed to the terminal.

## Configuration

- `ALERT_PERCENT_DROP`: drop threshold versus the previous rolling average (default `5.0`).
- `HISTORY_WINDOW`: number of previous samples included in that average (default `12`).
- `DB_PATH`: SQLite file for samples (default `market_history.db`).
- `SMTP_USE_SSL=true`: use SMTP over SSL (commonly port 465). For STARTTLS, set it to `false` and use the provider's STARTTLS port (commonly 587).
- `MARKET_CONTEXT`: optional note appended to alert emails. Time-sensitive market commentary should be updated before use; it is not treated as live market data by the script.

## Schedule with cron

Run every 30 minutes by adding an entry similar to this to your crontab, replacing paths as appropriate:

```cron
*/30 * * * * /path/to/project/.venv/bin/python /path/to/project/market_alert.py >> /path/to/project/market_alert.log 2>&1
```

## Market data and limitations

The COMEX quote is a Yahoo Finance futures quote and may not match the official settlement. MCX data requires a valid provider endpoint or symbol. The program compares each market with its own recent average; it does not convert currencies, compute Chennai retail rates, or guarantee a price prediction. Verify live quotes and retail prices with a current source before making decisions.
