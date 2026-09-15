# Деплой Trade-bot на VPS (Aeza) — пошагово

Для новичков. Сервер в EU → Telegram и биржи работают **без прокси**.

---

## Часть 1. Покупка сервера на Aeza

### 1.1 Регистрация

1. Открой **https://aeza.net** (именно `.net`, не `.ru` — там EU-серверы).
2. Нажми **Sign up** / **Регистрация**.
3. Введи email и пароль → подтверди почту.

### 1.2 Создание VPS

1. Войди в личный кабинет: **https://my.aeza.net**
2. Слева **«Добавить услугу +»** или плитка **«Виртуальный сервер»**.
3. Заполни форму:

| Поле | Что выбрать |
|------|-------------|
| Название | `lobster-bot` (любое) |
| Локация | **Amsterdam (NL)** или **Helsinki (FI)** |
| Тариф | **Shared** — самый дешёвый (1 vCPU, 1 GB RAM) |
| ОС | **Ubuntu 22.04** или **24.04** |
| Период | 1 месяц |
| Бэкапы | можно выключить (сделаем сами) |

4. Нажми **Оплатить** → пополни баланс картой / **СБП**.
5. Через 1–3 минуты сервер появится в **«Мои услуги»**.

### 1.3 Данные для входа

1. Открой сервер → вкладка **«Информация»**.
2. Запиши:
   - **IP-адрес** (например `185.xxx.xxx.xxx`)
   - **Логин:** `root`
   - **Пароль:** (кнопка «Показать пароль» или письмо на почту)

---

## Часть 2. Подключение с Windows

### Вариант A — PowerShell (встроен в Windows)

1. `Win + X` → **Терминал** или **Windows PowerShell**.
2. Команда (подставь свой IP):

```powershell
ssh root@185.xxx.xxx.xxx
```

3. При первом подключении спросит `Are you sure...` → введи **`yes`**.
4. Введи пароль root (символы не отображаются — это нормально).

Если видишь `root@lobster-bot:~#` — ты на сервере.

### Вариант B — PuTTY (если PowerShell не работает)

1. Скачай: https://www.putty.org/
2. Host Name: IP сервера, Port: `22`, Connection type: **SSH** → **Open**.
3. Login: `root`, Password: из панели Aeza.

---

## Часть 3. Первичная настройка сервера

Копируй команды **по одной строке** или блоками в SSH-окно.

```bash
apt update && apt upgrade -y
```

```bash
apt install -y python3 python3-pip python3-venv git nano
```

```bash
adduser botuser
```

- Придумай пароль для `botuser` (можно простой, SSH всё равно под root).
- На все вопросы Full Name / Phone — просто **Enter**.

```bash
mkdir -p /opt/trade-bot
chown botuser:botuser /opt/trade-bot
```

---

## Часть 4. Скачать код с GitHub

Репозиторий **приватный** — нужен токен GitHub.

### 4.1 Создать токен (один раз, на компьютере)

1. https://github.com/settings/tokens
2. **Generate new token** → **Generate new token (classic)**
3. Note: `aeza-deploy`
4. Scope: галочка **`repo`**
5. **Generate token** → скопируй токен (показывается один раз!)

### 4.2 Клонировать на сервере

Под `root` или переключись на botuser:

```bash
su - botuser
cd /opt/trade-bot
```

Команда (подставь **СВОЙ_ТОКЕН** вместо `ghp_xxxx`):

```bash
git clone https://ghp_ВАШ_ТОКЕН@github.com/EgorSandalov/Trade-bot.git .
```

> Точка в конце важна — клонируем прямо в `/opt/trade-bot`.

---

## Часть 5. Настройка `.env`

```bash
cd /opt/trade-bot
cp .env.example .env
nano .env
```

Заполни (пример):

```env
BOT_TOKEN=8994849492:AAH...
COMMUNITY_NAME=Lobster
ADMIN_IDS=1081923052
GROUPS=-1004429721352:3:1:trades.db;-1003842379589:24101:1:trades_prod.db;-1003884011519:2:1:trades_beta.db
PROFILES_DATABASE_PATH=data/profiles.db
BREAKEVEN_THRESHOLD_PCT=0.2
```

**Важно для сервера в EU:**
- строку `PROXY_URL=...` **удали** или закомментируй `#`

Сохранить в nano: `Ctrl+O` → Enter → `Ctrl+X`.

Проще: скопируй `.env` с домашнего ПК (см. часть 7).

---

## Часть 6. Установка и первый запуск

```bash
cd /opt/trade-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data
```

Проверка (бот должен стартовать без ошибок):

```bash
python -m bot.main
```

В Telegram напиши боту `/start` или в группе `/trades`.

Остановить тест: `Ctrl+C`.

---

## Часть 7. Перенос базы альфы (опционально)

Если нужна история сделок с локального ПК.

**На Windows** (новое окно PowerShell, не SSH):

```powershell
scp "C:\Users\Банан\Documents\GitHub\EgorSandalov\trade_bot\trades.db" root@185.xxx.x.xxx:/opt/trade-bot/
scp "C:\Users\Банан\Documents\GitHub\EgorSandalov\trade_bot\data\profiles.db" root@185.xxx.x.xxx:/opt/trade-bot/data/
```

На сервере:

```bash
chown botuser:botuser /opt/trade-bot/trades.db
chown botuser:botuser /opt/trade-bot/data/profiles.db
```

---

## Часть 8. Автозапуск (systemd)

Выйди из botuser: `exit` (должен быть `root@...`).

```bash
nano /etc/systemd/system/trade-bot.service
```

Вставь:

```ini
[Unit]
Description=Lobster Trade Telegram Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/trade-bot
Environment=PATH=/opt/trade-bot/.venv/bin
ExecStart=/opt/trade-bot/.venv/bin/python -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохрани: `Ctrl+O`, Enter, `Ctrl+X`.

```bash
systemctl daemon-reload
systemctl enable trade-bot
systemctl start trade-bot
systemctl status trade-bot
```

Должно быть **`active (running)`** зелёным.

### Полезные команды

| Действие | Команда |
|----------|---------|
| Логи в реальном времени | `journalctl -u trade-bot -f` |
| Перезапуск | `systemctl restart trade-bot` |
| Остановить | `systemctl stop trade-bot` |
| Статус | `systemctl status trade-bot` |

---

## Часть 9. Обновление бота после изменений

```bash
su - botuser
cd /opt/trade-bot
git pull
source .venv/bin/activate
pip install -r requirements.txt
exit
systemctl restart trade-bot
```

---

## Часть 10. Бэкап (раз в неделю)

```bash
mkdir -p /opt/backups
cp /opt/trade-bot/trades.db /opt/backups/trades_$(date +%F).db
cp /opt/trade-bot/trades_prod.db /opt/backups/ 2>/dev/null
cp /opt/trade-bot/trades_beta.db /opt/backups/ 2>/dev/null
cp /opt/trade-bot/data/profiles.db /opt/backups/profiles_$(date +%F).db
```

---

## Часть 11. Чеклист «всё работает»

- [ ] `systemctl status trade-bot` → active (running)
- [ ] В группе `/trades` отвечает
- [ ] `/leaderboard` открывается
- [ ] Новый сетап в ветке Setups → бот отвечает reply
- [ ] В `.env` нет `PROXY_URL`

---

## Частые проблемы

| Симптом | Решение |
|---------|---------|
| `Repository not found` при git clone | Проверь токен GitHub и scope `repo` |
| `Permission denied (publickey)` при ssh | Проверь IP и пароль в панели Aeza |
| Бот не отвечает | `journalctl -u trade-bot -f` — смотри ошибку |
| `Cannot reach Telegram API` | Убери PROXY_URL из .env на EU-сервере |
| Бот не видит группу | Проверь GROUPS в .env, бот должен быть в группе |

---

## Ссылки

- Aeza (регистрация EU): https://aeza.net
- Панель Aeza: https://my.aeza.net
- Репозиторий: https://github.com/EgorSandalov/Trade-bot
- GitHub токены: https://github.com/settings/tokens
- PuTTY: https://www.putty.org/
