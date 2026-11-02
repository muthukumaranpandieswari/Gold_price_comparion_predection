# Gold Price Comparison Email Alerts

A small Python monitor that records MCX India and COMEX gold prices, compares each new sample with its recent history, and emails an alert when a market drops by the configured threshold. WhatsApp/Twilio notifications have been replaced with SMTP email.

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

   Edit `.env` and set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `EMAIL_FROM`. `EMAIL_TO` is set to `hapieeji@gmail.com` in the sample; change it if desired. Use an app password if your email provider requires one. Set `MCX_PRICE_API_URL` to a provider that returns the current MCX gold price, or set `MCX_SYMBOL` if using Yahoo Finance. COMEX defaults to the Yahoo Finance `GC=F` chart endpoint.

3. Verify SMTP by sending a test email to the configured `EMAIL_TO` address:

   ```bash
   python3 market_alert.py --test-email
   ```

   A successful run confirms that the SMTP server accepted the message; check the recipient's inbox and spam folder to confirm delivery. Do not share SMTP passwords in chat or commit them to the repository.

4. Run a price check:

   ```bash
   python3 market_alert.py
   ```

Email alerts are sent only after enough price history exists to detect a drop. The `--test-email` option tests email delivery without fetching prices.

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
