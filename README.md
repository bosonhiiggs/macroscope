# T-068 — Интеграция распознавания номеров с журналом въездов/выездов

## Что сделано

Реализована серверная интеграция между IP-камерой распознавания номеров **Dahua DHI-ITC413-PW4D-IZ3** и системой учёта въездов/выездов транспортных средств. Камера в режиме реального времени распознаёт номерные знаки и передаёт события в нашу систему, которая автоматически создаёт записи в журнале.

Django-проект является самостоятельным sandbox-приложением, подготовленным для последующего переноса в основной репозиторий Steiza.

---

## Архитектура

```
Камера Dahua ITC413
(распознавание на чипе)
        │
        │  HTTP multipart-поток событий
        │  (eventManager.cgi, Digest Auth)
        ▼
  Dahua-воркер
  (dahua_stream_worker.py)
        │
        │  ParsedPlateEvent
        ▼
  Обработчик событий
  (event_processor.py)
        │
        ├─ фильтрация по достоверности
        ├─ идемпотентность по EventID
        ├─ дедупликация в окне 60 сек
        └─ создание VehicleGatePass
                │
                ▼
           SQLite / PostgreSQL
```

**Примечание по Macroscop:** сервер Macroscop 4.6 установлен, но у него нет GPU для работы модуля ANPR. Поэтому распознавание выполняется непосредственно на камере, а интеграция идёт напрямую с камерой, минуя Macroscop. Код интеграции с Macroscop также реализован и готов к активации после получения лицензионного ключа.

---

## Структура проекта

```
macroscope/                          # Django-проект
├── terminal/                        # Модель терминала (мультитенантность)
├── vehicle_fleet/                   # Основная бизнес-логика
│   ├── models.py                    # FleetVehicle, GateCamera, VehicleGatePass
│   ├── views.py / urls.py           # REST API
│   ├── serializers.py
│   ├── services.py                  # PlateNormalizer, FleetVehicleService
│   └── constants.py                 # GateCameraRole, GatePassDirection
└── vehicle_fleet_integration/       # Инфраструктура интеграции
    ├── dahua_client.py              # HTTP-клиент Dahua (Digest Auth, multipart)
    ├── dahua_event_parser.py        # Разбор событий камеры → ParsedPlateEvent
    ├── dahua_stream_worker.py       # Долгоживущий цикл чтения с реконнектом
    ├── event_processor.py           # Общий алгоритм обработки (Dahua + Macroscop)
    ├── client.py                    # HTTP-клиент Macroscop (Basic Auth + MD5)
    ├── event_parser.py              # Разбор событий Macroscop
    ├── stream_worker.py             # Воркер Macroscop
    └── management/commands/
        └── run_macroscop_integration.py   # Точка входа (management command)
```

---

## REST API

Базовый URL: `http://<host>/api/terminals/<terminal_id>/`

Аутентификация: Basic Auth или Session.

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `fleet-vehicles/` | Список автопарка |
| POST | `fleet-vehicles/` | Добавить транспортное средство |
| GET / PATCH / DELETE | `fleet-vehicles/<id>/` | Просмотр / изменение / удаление ТС |
| GET | `vehicle-gate-passes/` | Журнал въездов/выездов |
| POST | `vehicle-gate-passes/` | Добавить запись вручную |
| GET | `vehicle-gate-passes/<id>/` | Просмотр записи |
| GET / POST | `gate-cameras/` | Список камер / добавить камеру |
| GET / PATCH | `gate-cameras/<id>/` | Просмотр / изменение камеры |

Список журнала поддерживает фильтрацию: `date_from`, `date_to`, `direction`, `registration_number`, `source`.

---

## Алгоритм обработки событий

Каждое событие от камеры проходит следующие шаги:

1. **Фильтр достоверности** — если уверенность камеры ниже порога (по умолчанию 60%), событие отбрасывается.
2. **Идемпотентность** — если запись с таким `EventID` уже есть в БД, дубликат не создаётся.
3. **Нормализация номера** — привод к верхнему регистру, удаление пробелов и дефисов.
4. **Поиск камеры** — сопоставление события с объектом `GateCamera` по `ChannelId`.
5. **Определение направления** — из поля события (`DrivingDirection`); при отсутствии — из роли камеры (`entry`/`exit`).
6. **Мягкая дедупликация** — пропуск, если аналогичная запись уже есть в окне 60 секунд.
7. **Поиск ТС** — попытка привязать к записи в справочнике автопарка.
8. **Создание `VehicleGatePass`** — запись в БД, обновление курсора состояния интеграции.

---

## Модели данных

### FleetVehicle — справочник автопарка
| Поле | Тип | Описание |
|------|-----|----------|
| `terminal` | FK | Терминал |
| `registration_number` | str | Номерной знак (нормализован) |
| `brand` / `model` | str | Марка/модель |
| `is_active` | bool | Мягкое удаление |

### GateCamera — камера на КПП
| Поле | Тип | Описание |
|------|-----|----------|
| `terminal` | FK | Терминал |
| `macroscop_channel_id` | UUID | ID канала в Macroscop / Dahua |
| `name` | str | Название |
| `role` | choice | `entry` (въезд) / `exit` (выезд) |

### VehicleGatePass — журнал проездов
| Поле | Тип | Описание |
|------|-----|----------|
| `terminal` | FK | Терминал |
| `registration_number` | str | Номерной знак |
| `direction` | choice | `entry` / `exit` |
| `passed_at` | datetime | Время проезда (UTC) |
| `source` | choice | `macroscop` / `manual` |
| `reliability` | float | Достоверность распознавания (0.0–1.0) |
| `fleet_vehicle` | FK nullable | Привязка к автопарку |
| `gate_camera` | FK nullable | Камера, зафиксировавшая проезд |
| `macroscop_event_id` | UUID unique | Ключ идемпотентности |
| `raw_event` | JSON | Полное тело события от камеры |

---

## Настройка и запуск

### Зависимости

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Переменные окружения (`macroscope/.env`)

```env
# Dahua-камера
DAHUA_BASE_URL=http://195.19.150.181:8000
DAHUA_LOGIN=admin
DAHUA_PASSWORD=<пароль>
DAHUA_MIN_RELIABILITY=0.60

# Macroscop (активируется после получения лицензии)
MACROSCOP_ENABLED=True
MACROSCOP_BASE_URL=http://195.19.150.181:8080
MACROSCOP_LOGIN=root
MACROSCOP_PASSWORD_MD5=<md5-хеш пароля>
MACROSCOP_TERMINAL_ID=2
MACROSCOP_MIN_RELIABILITY=0.85
```

Никогда не коммитить `.env` с реальными данными — файл добавлен в `.gitignore`.

### Первый запуск

```bash
cd macroscope
python manage.py migrate
python manage.py createsuperuser
```

### Запуск воркера (прямое подключение к Dahua-камере)

```bash
nohup python manage.py run_macroscop_integration \
    --terminal-id=2 --source=dahua --gate-camera-id=2 \
    > /tmp/dahua_integration.log 2>&1 &
```

---

## Технические особенности Dahua ITC413

### Временны́е метки

Камера передаёт **два** поля с временем:
- `UTC` — несмотря на название, содержит **местное время (МСК)**, а не UTC.
- `RealUTC` — действительное UTC-время. Используем это поле.

Разница между ними всегда ровно 3 часа (смещение UTC+3).

### Направление движения

Поле `TrafficCar.DrivingDirection[0]`:
- `"Leave"` → выезд (`exit`)
- `"Approach"` → въезд (`entry`)

### EventID

В Dahua — целое число (не UUID). Конвертируется в UUID через `uuid.UUID(int=EventID)` для хранения в поле `macroscop_event_id`.

---

## Рекомендации по улучшению точности камеры

Следующие настройки требуют доступа в веб-интерфейс или Dahua SmartPSS (задача для Александра):

1. **Страна/формат номеров** — установить Россия (RU). Камера сейчас распознаёт номера как иностранные (PSE, NOR, NLD), что снижает точность.
2. **Зона распознавания** — убедиться, что зона охватывает номерной знак полностью. Наблюдается потеря первой буквы у ряда номеров.
3. **Угол установки** — камера оптимально работает при угле не более 30° от оси движения.
4. **Ночная подсветка** — настроить ИК-подсветку или стробоскоп для снижения количества ложных срабатываний от бликов фар.

---

## Статус Macroscop

Сервер Macroscop 4.6 установлен и доступен по адресу `195.19.150.181:8080`, но возвращает `401` — лицензионный ключ ещё не активирован. Как только ключ будет получен и Александр настроит API-пользователя:

1. Внести в `.env` значения `MACROSCOP_LOGIN` и `MACROSCOP_PASSWORD_MD5`.
2. Получить у Александра UUID каналов камер въезда/выезда и UUID типа события «Обнаружен автономер».
3. Переключить запуск воркера на `--source=macroscop`.

Код интеграции с Macroscop полностью реализован и готов.