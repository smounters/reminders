# ТЗ: GTK-напоминалка (Python) с гибким расписанием и .deb-сборкой

> Документ предназначен для исполнения агентом (Claude Code). Цель — собрать
> десктопное приложение-напоминалку для Linux Mint (Cinnamon) / Ubuntu с
> гибким расписанием, иконкой в трее, уведомлениями и пакетированием в `.deb`.

---

## 1. Обзор и цель

Приложение позволяет создавать напоминания и получать desktop-уведомления по
гибкому расписанию: разовые (конкретная дата/время), интервальные (каждые N
минут/часов) и календарные (дни недели + время / cron-выражение). Работает как
фоновый трей-апплет, переживает перезагрузку (автозапуск), хранит задачи
локально.

Рабочее имя проекта: **Reminders** (пакет `reminders-gtk`).
App-ID (reverse-DNS, для `.desktop`/иконок/single-instance): `cc.vocatio.Reminders`
— **TODO: подтвердить у владельца** (см. §18).

---

## 2. Целевая платформа и стек

- **ОС:** Linux Mint 22 (Cinnamon) и Ubuntu 24.04+. Должно работать на X11 и
  Wayland.
- **Python:** 3.10+ (целевой — 3.12 из репозитория Ubuntu 24.04).
- **GUI:** GTK **3** + PyGObject (`gi`). GTK3 выбран осознанно: на Cinnamon
  стабильнее работают трей-индикатор и уведомления, чем на GTK4.
- **Трей:** AppIndicator с авто-фолбэком `AyatanaAppIndicator3` → `AppIndicator3`.
- **Уведомления:** libnotify через `gi.repository.Notify`.
- **Звук:** системный, проигрывается самим демоном уведомлений (без отдельного
  аудиоплеера и доп. зависимостей) — см. §7.
- **Расписание:** APScheduler (`BackgroundScheduler`). **Код пишется строго под
  API APScheduler 3.x** — именно эта мажорная версия лежит в репозиториях всех
  целевых дистрибутивов; 4.x это несовместимый рерайт, его не используем.
- **Хранилище:** SQLite через stdlib `sqlite3` (без тяжёлой ORM).
- **Даты/время:** `python-dateutil`, таймзоны — `zoneinfo` (stdlib).
- **Линт/формат:** `ruff` (lint + format).

Все рантайм-зависимости должны быть доступны как системные deb-пакеты, чтобы не
тянуть pip внутрь `.deb` (см. §11): `python3-gi`, `gir1.2-gtk-3.0`,
`gir1.2-ayatanaappindicator3-0.1` (с альтернативой `gir1.2-appindicator3-0.1` —
см. §11), `gir1.2-notify-0.7`, `python3-apscheduler`, `python3-dateutil`.

**Принцип кросс-дистро совместимости:** версии этих пакетов различаются по
дистрибутивам, поэтому код пишется под наименьший общий API (в первую очередь это
касается APScheduler 3.x и импорта AppIndicator с фолбэком). Целевая матрица —
Debian 12/13, Ubuntu 22.04/24.04 (и Mint, который наследует базу Ubuntu LTS).

---

## 3. Архитектура

Модульная структура внутри пакета `reminders/`:

- `app.py` — `Gtk.Application` (single-instance по application-id), точка входа,
  инициализация трея и фонового планировщика.
- `models.py` — dataclass `Reminder` и enum типов расписания.
- `storage.py` — слой доступа к SQLite (CRUD задач, миграции схемы по версии).
- `scheduler.py` — обёртка над APScheduler: маппинг `Reminder` → trigger,
  регистрация/снятие задач, вычисление `next_run`.
- `tray.py` — индикатор и его меню.
- `windows/main_window.py` — главное окно со списком напоминаний.
- `windows/edit_dialog.py` — диалог создания/редактирования.
- `windows/settings_dialog.py` — глобальные настройки.
- `notifier.py` — обёртка над Notify (показ, кнопки-действия, snooze).
- `autostart.py` — управление `~/.config/autostart/<appid>.desktop`.
- `paths.py` — XDG-пути (config/data/state).
- `__main__.py` — `python -m reminders`.

**CLI-флаг самопроверки (для CI):** приложение поддерживает неинтерактивный режим
`python -m reminders --selftest`, который инициализирует GTK/Notify/AppIndicator,
создаёт планировщик, регистрирует тестовую задачу, проверяет вычисление `next_run`
и завершается с кодом `0` (или `≠0` при ошибке), **не входя в `Gtk.main()`**. Этот
режим используется в install-матрице CI под `xvfb` (см. §13).

**Потоковая модель (критично):** APScheduler крутит задачи в фоновом потоке.
Любой вызов GTK/Notify из колбэка задачи обязан маршалиться в главный поток через
`GLib.idle_add(...)`. Прямые вызовы GTK из потока планировщика запрещены.

---

## 4. Модель данных

Таблица `reminders` (SQLite):

| поле           | тип      | описание                                                        |
|----------------|----------|-----------------------------------------------------------------|
| `id`           | TEXT PK  | UUIDv4                                                           |
| `title`        | TEXT     | заголовок уведомления                                            |
| `message`      | TEXT     | тело уведомления                                                 |
| `enabled`      | INTEGER  | 0/1                                                              |
| `sound`        | INTEGER  | 0/1 — проигрывать звук                                           |
| `sched_type`   | TEXT     | `once` \| `interval` \| `weekly` \| `cron`                      |
| `sched_params` | TEXT     | JSON с параметрами расписания (см. ниже)                         |
| `created_at`   | TEXT     | ISO8601                                                          |
| `updated_at`   | TEXT     | ISO8601                                                          |

Формат `sched_params` по типам:
- `once`: `{ "run_at": "2026-06-01T09:30:00" }` (локальная TZ).
- `interval`: `{ "every": 60, "unit": "minutes", "start_at": "..."|null }`.
- `weekly`: `{ "days": ["mon","wed","fri"], "time": "09:00" }`
  (допускается несколько времён: `"times": ["09:00","18:00"]`).
- `cron`: `{ "expr": "0 * * * *" }`.

Глобальные настройки — отдельная таблица `settings` (ключ/значение) или JSON-файл
`config.json`: тихие часы, дефолтный звук, таймзона (по умолчанию системная).

---

## 5. Движок расписания

Маппинг `Reminder.sched_type` → APScheduler trigger:

- `once` → `DateTrigger(run_date=run_at)`. После срабатывания задача
  автоматически помечается `enabled=0` (разовая отработала).
- `interval` → `IntervalTrigger(minutes=…/hours=…, start_date=start_at)`.
- `weekly` → `CronTrigger(day_of_week="mon,wed,fri", hour=…, minute=…)`.
  Несколько времён → несколько APScheduler-джоб на один `Reminder`.
- `cron` → `CronTrigger.from_crontab(expr)`.

Требования:
- При старте приложения планировщик **пересобирается** из SQLite (APScheduler
  работает in-memory, persistent jobstore не используем — это снимает проблему
  пиклинга колбэков).
- Каждая джоба вызывает единый диспетчер `fire(reminder_id)`, который читает
  актуальные данные задачи из storage и через `GLib.idle_add` показывает
  уведомление.
- Для каждой задачи в UI показывать `next_run` (брать у APScheduler
  `job.next_run_time`).
- Глобальная «Пауза» — `scheduler.pause()`, снимает все срабатывания, статус
  отражается в трее.
- Тихие часы (опц., фаза 2): если время попадает в интервал тишины — уведомление
  не показывается (или откладывается до конца тишины).

---

## 6. GUI

### Главное окно
- `Gtk.TreeView`/`Gtk.ListBox` со списком задач. Колонки: чекбокс `enabled`,
  заголовок, человекочитаемое описание расписания (например «Каждый час»,
  «Пн/Ср/Пт в 09:00», «01.06.2026 09:30»), `next_run`.
- Тулбар: Добавить, Изменить, Удалить, Дублировать.
- Двойной клик по строке — открыть редактирование.
- Окно по закрытию (X) сворачивается в трей, а не выходит из приложения.

### Диалог создания/редактирования (`edit_dialog.py`)
- Поля: Заголовок, Текст, чекбоксы «Звук», «Включено».
- Выбор типа расписания (`Gtk.StackSwitcher` или combo), под каждый тип — свой
  набор контролов:
  - **Один раз:** выбор даты (`Gtk.Calendar`) + времени (spin часы/минуты).
  - **Каждые N:** spin + единица (минуты/часы).
  - **По дням недели:** 7 чекбоксов Пн–Вс + поле времени (с возможностью добавить
    несколько времён).
  - **Cron (advanced):** текстовое поле с валидацией выражения и подсказкой.
- Валидация: разовая задача в прошлом — предупреждение; пустой заголовок —
  подставлять дефолт.

### Трей (`tray.py`)
- Меню: статус («Следующее: HH:MM» / «На паузе»), Открыть окно,
  Пауза/Возобновить, Добавить напоминание…, Настройки…, Выход.

### Настройки (`settings_dialog.py`)
- Автозапуск (галочка ↔ `.desktop` в autostart).
- Звук уведомления вкл/выкл (системный, см. §7).
- Тихие часы (с/по).
- Таймзона (по умолчанию системная).

---

## 7. Уведомления и snooze

- Показ через `Notify.Notification`. Для разовых — `Urgency.NORMAL`.
- **Snooze:** если окружение поддерживает действия в уведомлениях, добавлять
  кнопку «Отложить 10 мин» (`notification.add_action(...)`), по нажатию —
  создавать временную `once`-джобу через +10 минут. Кнопки-действия требуют, чтобы
  GLib main loop был активен (он активен — это GTK-приложение).
- **Звук:** системный, делегируется демону уведомлений через hint
  `notification.set_hint_string("sound-name", "message")` (freedesktop Sound
  Naming Spec). Отдельный аудиоплеер и звуковые файлы не используются. Если задача
  создана с выключенным звуком — hint не выставляется. Поведение при беззвучном
  режиме ОС определяется демоном уведомлений (это ожидаемо и приемлемо).

---

## 8. Хранение и пути (XDG)

Использовать XDG через `GLib.get_user_*` или `paths.py`:
- Конфиг: `~/.config/<appid>/config.json`
- Данные (БД): `~/.local/share/<appid>/reminders.db`
- Состояние/логи: `~/.local/state/<appid>/app.log`

Схема БД версионируется (`PRAGMA user_version`), при старте — миграции вперёд.

---

## 9. Автозапуск

`autostart.py` создаёт/удаляет `~/.config/autostart/<appid>.desktop` с
`Exec=<команда запуска>` и `X-GNOME-Autostart-enabled=true`. Команда запуска после
установки `.deb` — это установленный исполняемый entry point (например
`/usr/bin/reminders-gtk`), а не путь к исходнику.

---

## 10. Структура репозитория

```
reminders-gtk/
├── pyproject.toml            # метаданные, entry point reminders-gtk = reminders.app:main
├── README.md
├── LICENSE                   # Apache-2.0 (полный текст)
├── NOTICE                    # атрибуция (Apache-2.0), упоминание Lucide/ISC для иконок
├── reminders/                # пакет (см. §3)
│   ├── __init__.py
│   ├── __main__.py
│   └── ...
├── data/
│   ├── cc.vocatio.Reminders.desktop        # ярлык приложения (.desktop)
│   ├── cc.vocatio.Reminders.metainfo.xml   # AppStream-метаданные
│   └── icons/hicolor/scalable/apps/cc.vocatio.Reminders.svg  # stub-иконка (Lucide, ISC)
├── debian/                   # см. §11
│   ├── control
│   ├── rules
│   ├── changelog
│   ├── copyright             # DEP-5: код Apache-2.0, иконки ISC
│   ├── install
│   └── source/format
├── packaging/
│   └── build-deb.sh          # ОПЦИОНАЛЬНО: локальная сборка для отладки
├── .github/workflows/
│   ├── ci.yml                # lint + unit + сборка + install-матрица (§13)
│   └── release.yml           # сборка + публикация в Releases по тегу (§13)
└── tests/                    # pytest: логика расписания, описания, миграции
```

В `pyproject.toml` указать `license = "Apache-2.0"` (SPDX) и заголовки лицензии в
исходниках по желанию.

---

## 11. Сборка `.deb`

**Подход:** нативный Debian-пакет через `debhelper` + `dh-python` (`pybuild`).
Пакет `Architecture: all` (чистый Python, без компилируемых расширений) — один
артефакт ставится на всю целевую матрицу дистрибутивов.

**Где собираем:** основная сборка — **в CI, в контейнере самого старого таргета
(`debian:12`)**. Это держит автогенерируемую нижнюю границу `python3` низкой, иначе
сборка на новом Python (напр. 3.12) может проставить `python3 (>= 3.12)` и пакет не
встанет на Debian 12. Локальная сборка — только для отладки (опциональный
`packaging/build-deb.sh`), в обычном цикле не нужна (см. §13).

`debian/control` (черновик):
```
Source: reminders-gtk
Section: utils
Priority: optional
Maintainer: <Имя> <email>
Build-Depends: debhelper-compat (= 13), dh-python, python3-all, pybuild-plugin-pyproject
Standards-Version: 4.6.2

Package: reminders-gtk
Architecture: all
Depends: ${python3:Depends}, ${misc:Depends},
 python3-gi, gir1.2-gtk-3.0,
 gir1.2-ayatanaappindicator3-0.1 | gir1.2-appindicator3-0.1,
 gir1.2-notify-0.7, python3-apscheduler, python3-dateutil
Description: GTK reminder app with flexible scheduling
 Tray reminder application supporting one-time, interval and
 calendar-based reminders with desktop notifications.
```

> **Важно — альтернативная зависимость:**
> `gir1.2-ayatanaappindicator3-0.1 | gir1.2-appindicator3-0.1`. Имя GIR-пакета
> AppIndicator плавает по дистрибутивам; альтернатива заставляет apt взять то, что
> есть. Это зеркалит фолбэк импорта в коде (§2/§3).

`debian/rules`:
```
#!/usr/bin/make -f
%:
	dh $@ --with python3 --buildsystem=pybuild
```

`debian/install` — раскладка data-файлов:
```
data/cc.vocatio.Reminders.desktop        usr/share/applications/
data/cc.vocatio.Reminders.metainfo.xml   usr/share/metainfo/
data/icons/hicolor/scalable/apps/cc.vocatio.Reminders.svg usr/share/icons/hicolor/scalable/apps/
```

`debian/copyright` — формат DEP-5: код проекта под **Apache-2.0**, stub-иконки под
их лицензией (ISC для Lucide — см. §14).

После сборки CI должен проверить сгенерированную строку `Depends` (через
`dpkg-deb -f *.deb Depends`) и убедиться, что нет жёсткого пина `python3 (>= 3.12)`
или подобного — это часть проверки кросс-дистро совместимости.

---

## 12. Публикация

**Решение: только GitHub Releases с прикреплённым `.deb`-ассетом.** Репозиторий
публичный, поэтому минуты GitHub Actions бесплатны — сборка и публикация полностью
автоматизированы в CI.

Как работает:
- CI по push тега `v*` собирает `.deb` (`dpkg-buildpackage -b`) и прикрепляет его
  как asset к соответствующему GitHub Release.
- Установка пользователем: скачать файл и
  `sudo apt install ./reminders-gtk_<версия>_all.deb` (apt дотянет зависимости).
- В README — раздел «Установка» с прямой ссылкой на последний релиз и командой.

Ограничение, которое осознанно принимаем: **авто-обновлений нет** — apt не знает о
новых версиях, пользователь обновляется вручную, скачивая новый `.deb`. Для
публичного pet-проекта на старте этого достаточно.

> **На будущее (вне текущих рамок), если появится постоянная аудитория и захочется
> авто-обновлений:** Launchpad PPA (привычно для Ubuntu/Mint, сборка из source на
> стороне Canonical) либо собственный apt-репозиторий через `aptly`/`reprepro` на
> своём сервере (S3 + CloudFront как дешёвый статичный хостинг). OpenSUSE Build
> Service — если понадобится охват многих дистрибутивов. Snap не рассматриваем (на
> Mint snapd заблокирован по умолчанию); Flatpak потребовал бы порталов для трея и
> автозапуска.

---

## 13. CI/CD (GitHub Actions)

Вся сборка и проверки — в GitHub Actions (репозиторий публичный → минуты
бесплатны). Локальная сборка не входит в обычный цикл. Два workflow-файла:

### `.github/workflows/ci.yml` — на каждый push и pull_request

Джобы:

1. **lint-and-unit** (runner `ubuntu-latest`):
   - `ruff check .` + `ruff format --check .`.
   - `pytest` — юнит-тесты без GUI: маппинг `Reminder` → APScheduler trigger,
     вычисление `next_run`, человекочитаемые описания расписания, миграции БД.

2. **build-deb** (контейнер `debian:12` — самый старый таргет, чтобы не задрать
   нижнюю границу `python3`):
   - ставит build-deps (`debhelper`, `dh-python`, `pybuild-plugin-pyproject`,
     `devscripts`, `build-essential`);
   - `dpkg-buildpackage -us -uc -b`;
   - проверяет `Depends` собранного пакета (`dpkg-deb -f *.deb Depends`) на
     отсутствие жёсткого пина версии Python;
   - выгружает `.deb` как artifact (`actions/upload-artifact`).

3. **test-install** (matrix, `needs: build-deb`):
   - `strategy.matrix.image: [debian:12, debian:13, ubuntu:22.04, ubuntu:24.04]`,
     каждая джоба запускается в соответствующем `container:`;
   - скачивает artifact с `.deb` (`actions/download-artifact`);
   - `apt-get update && apt-get install -y ./reminders-gtk_*.deb` — проверяет, что
     зависимости (включая альтернативу appindicator) резолвятся из штатных репозиториев
     каждого дистрибутива;
   - ставит `xvfb`, `dbus-x11` и запускает headless-самопроверку:
     `xvfb-run -a dbus-run-session -- reminders-gtk --selftest` (ожидается код 0);
   - Mint в матрицу не добавляем — он наследует базу Ubuntu LTS, зелёный Ubuntu
     гарантирует Mint.

### `.github/workflows/release.yml` — на push тега `v*`

- `permissions: contents: write`.
- **build-deb** в контейнере `debian:12` (как выше) → `.deb`.
- (рекомендуется) повторить **test-install**-матрицу как gate перед публикацией.
- **publish**: создать GitHub Release для тега и прикрепить `.deb`
  (`softprops/action-gh-release`). В тело релиза вставить команду установки.

Версия пакета берётся из тега (`v1.2.3` → `1.2.3`) и подставляется в
`debian/changelog` на лету (например через `dch`/скрипт), чтобы не держать версию
в двух местах.

---

## 14. Иконки и ассеты (stub)

- На время разработки приложение должно работать **без кастомных ассетов**:
  иконка трея и уведомлений — по имени из системной темы (`alarm-symbolic`,
  фолбэк `appointment-soon`).
- Иконку приложения (`.desktop`/AppStream) положить как **stub SVG из набора
  Lucide (лицензия ISC)** — пермиссивно и полностью совместимо с Apache-2.0 кода.
  Лицензию иконки отразить в `debian/copyright` (DEP-5) и README.
- Stub-иконка названа по app-id и легко заменяется позже на сгенерированную.
- В `metainfo.xml`: `<project_license>Apache-2.0</project_license>`,
  `<metadata_license>FSFAP</metadata_license>`.

---

## 15. Требования к качеству

- **Single-instance:** через `Gtk.Application` с `application_id` и флагом — второй
  запуск активирует уже работающий экземпляр (открывает окно), а не плодит трей.
- **Логирование:** stdlib `logging` в файл состояния + stderr; уровень
  настраивается переменной окружения `REMINDERS_LOG=DEBUG`.
- **Обработка ошибок:** падение показа уведомления / звука не должно ронять
  приложение; планировщик переживает исключения в задачах.
- **Потокобезопасность:** правило `GLib.idle_add` для всех GTK/Notify-вызовов из
  потока планировщика (см. §3) — соблюдать строго.
- **i18n (фаза 2):** строки централизовать, заложить `gettext`; интерфейс по
  умолчанию — русский, fallback — английский.
- **Тесты:** pytest на маппинг `Reminder` → trigger, человекочитаемые описания и
  миграции БД (без GUI); headless-самопроверка `--selftest` под `xvfb`+`dbus` в
  install-матрице CI по дистрибутивам (см. §13).

---

## 16. Фазы

**MVP (фаза 1):**
- CRUD напоминаний; типы `once`, `interval`, `weekly`.
- Трей, уведомления, системный звук, автозапуск, главное окно + диалог.
- Хранение в SQLite, пересборка планировщика при старте.
- Сборка `.deb` в CI (контейнер `debian:12`) + install-матрица по дистрибутивам +
  публикация в GitHub Releases по тегу.
- Лицензия Apache-2.0, stub-иконки Lucide (ISC).

**Фаза 2:**
- Тип `cron` (advanced) с валидацией.
- Snooze-кнопка в уведомлениях.
- Тихие часы.
- PPA и/или свой apt-репозиторий.
- i18n (gettext), кастомные иконки.

---

## 17. Критерии приёмки (Definition of Done)

1. `python -m reminders` запускает трей-приложение на чистой Mint 22.
2. Можно создать разовое, интервальное и понедельное напоминание; все три
   корректно срабатывают (уведомление появляется в нужное время).
3. `next_run` корректно отображается и обновляется в списке.
4. Пауза/возобновление работают; настройки и задачи сохраняются между запусками.
5. Автозапуск включается/выключается галочкой и реально стартует приложение при
   входе в сессию.
6. CI собирает устанавливаемый `.deb` в контейнере `debian:12`; install-матрица
   (`debian:12/13`, `ubuntu:22.04/24.04`) ставит его и проходит `--selftest`.
7. CI зелёный: lint + pytest + сборка + install-матрица; релиз по тегу `v*`
   публикует `.deb` в GitHub Releases.
8. Все ассеты имеют указанную лицензию в `debian/copyright` (код Apache-2.0,
   иконки ISC); в репозитории есть `LICENSE` и `NOTICE`.

---

## 18. Решения, которые нужно подтвердить у владельца

- **Лицензия:** ✅ решено — **Apache-2.0** (код), иконки Lucide под ISC. См. §14.
- **Публикация:** ✅ решено — только GitHub Releases с `.deb`-ассетом, репозиторий
  публичный (CI бесплатный). См. §12.
- **Матрица ОС:** ✅ решено — `debian:12`, `debian:13`, `ubuntu:22.04`,
  `ubuntu:24.04`; Mint покрывается базой Ubuntu LTS. См. §13.
- **Осталось подтвердить:** имя/бренд приложения и финальный **app-id** (предложено
  `cc.vocatio.Reminders`). Если оставить как есть — можно сразу отдавать в Claude
  Code.
