# Reminders (reminders-gtk)

GTK3 desktop reminder app for Linux Mint (Cinnamon) and Ubuntu with a flexible
scheduler, tray icon, desktop notifications and a `.deb` package.

- One-shot, interval, weekly and cron-based reminders.
- Lives in the system tray (AppIndicator, with Ayatana → legacy fallback).
- Desktop notifications via `libnotify`; system notification sound.
- Local SQLite storage; autostart via `~/.config/autostart`.
- Single-instance via `Gtk.Application` (`application_id =
  com.smounters.Reminders`).

## Installation

Download the latest `.deb` from
[GitHub Releases](https://github.com/smounters/reminders-gtk/releases) and
install it with `apt` so dependencies get pulled in automatically:

```sh
sudo apt install ./reminders-gtk_<version>_all.deb
```

The package targets Debian 12/13 and Ubuntu 22.04/24.04 (and therefore Linux
Mint, which inherits the Ubuntu LTS base).

## Running from source

```sh
sudo apt install python3-gi gir1.2-gtk-3.0 \
    gir1.2-ayatanaappindicator3-0.1 gir1.2-notify-0.7 \
    python3-apscheduler python3-dateutil
python3 -m reminders
```

A non-interactive self-check used by CI:

```sh
python3 -m reminders --selftest
```

## Build the .deb locally (optional)

```sh
./packaging/build-deb.sh
```

The standard build path is GitHub Actions in a `debian:12` container so the
auto-generated lower bound on `python3` stays low.

## License

- Code: [Apache License, Version 2.0](LICENSE)
- Stub icons (data/icons/): ISC, from the [Lucide](https://lucide.dev) icon set
- See [NOTICE](NOTICE) and `debian/copyright` for full attribution.
