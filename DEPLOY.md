# Деплой на VPS (непрерывный запуск на Binance testnet)

Бот должен работать 24/7 несколько недель. Ниже — через Docker (рекомендуется,
портативно) и альтернатива через systemd. Всё — на дешёвом Ubuntu-VPS.

Предпосылки: ключи Binance **Futures TESTNET** (см. `TESTNET.md`). Ключи вводите
только вы; в git и в образ они не попадают.

---

## Вариант A — Docker (рекомендуется)

### 1. VPS
Любой VPS с Ubuntu 22.04+ (1 vCPU / 1 GB RAM достаточно): Hetzner, DigitalOcean,
Vultr, Contabo и т.п. Подключитесь по SSH.

### 2. Установить Docker
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker   # чтобы docker без sudo
```

### 3. Забрать код (репозиторий публичный)
```bash
git clone https://github.com/kontekstlab-beep/CHBE.git
cd CHBE
```

### 4. Ключи в .env
```bash
cp .env.example .env
nano .env        # впишите BINANCE_TESTNET_KEY и BINANCE_TESTNET_SECRET
```
`.env` в git не попадёт (в .gitignore).

### 5. Предполётная проверка (без сделок)
```bash
docker compose run --rm bot python run_paper.py --check
```
Должно показать баланс USDT и число рынков. Нулевой баланс — пополните faucet-ом
на testnet.binancefuture.com.

### 6. Запуск в фоне (24/7)
```bash
docker compose up -d --build
```
`restart: unless-stopped` перезапустит бота при падении и после ребута VPS.

### Операции
```bash
docker compose logs -f              # живые логи (Ctrl+C — выйти, бот работает)
tail -f state/paper.log             # то же в файле (переживает пересоздание)
docker compose ps                   # статус
docker compose restart              # перезапуск
docker compose down                 # остановить
git pull && docker compose up -d --build   # обновить код
```
Состояние и логи — в `./state/` (том), переживают пересборку.

---

## Вариант B — systemd (без Docker)

```bash
git clone https://github.com/kontekstlab-beep/CHBE.git && cd CHBE
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-runtime.txt
```
Юнит `/etc/systemd/system/chbe-bot.service`:
```ini
[Unit]
Description=CHBE paper bot (mean-reversion, testnet)
After=network-online.target

[Service]
WorkingDirectory=/home/<user>/CHBE
Environment=BINANCE_TESTNET_KEY=ваш_ключ
Environment=BINANCE_TESTNET_SECRET=ваш_секрет
Environment=PAPER_STATE=/home/<user>/CHBE/state/paper_state.json
Environment=PAPER_LOG=/home/<user>/CHBE/state/paper.log
ExecStart=/home/<user>/CHBE/.venv/bin/python run_paper.py --live --testnet
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```
```bash
mkdir -p state
sudo systemctl daemon-reload
sudo systemctl enable --now chbe-bot
sudo systemctl status chbe-bot          # статус
journalctl -u chbe-bot -f               # логи
```

---

## Что дальше
Оставьте бота на 2–4 недели. Затем заберите `state/paper.log` и сравните с моделью
(fill rate лимиток, реальный P&L/сделку против бэктеста ~+0.12–0.15%). Это финальный
вердикт: живой ли edge на реальном исполнении.

> Безопасность: ключ — только фьючерсная торговля, БЕЗ вывода. Это testnet (не
> реальные деньги). На реал — только после устойчивого плюса и осознанно.
