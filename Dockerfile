# Образ для непрерывного paper-запуска mean-reversion на Binance testnet.
FROM python:3.12-slim

WORKDIR /app

# только рантайм-зависимость (ccxt); тесты/pandas/numpy для живого бота не нужны
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

# код бота (движок/логика/раннер). Данные data/ и smartmoney/ для --live не нужны.
COPY paper/ ./paper/
COPY run_paper.py .

# состояние и логи пишутся в /data (монтируется томом) — см. docker-compose.yml
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PAPER_STATE=/data/paper_state.json \
    PAPER_LOG=/data/paper.log

# ключи BINANCE_TESTNET_KEY/SECRET передаются через env (env_file .env), НЕ в образ
CMD ["python", "run_paper.py", "--live", "--testnet"]
