# tui-train-times

![Python](https://img.shields.io/badge/python-3.8+-blue?style=flat-square)
![License](https://img.shields.io/github/license/kaimrdth/tui-train-times?style=flat-square)
![Last Commit](https://img.shields.io/github/last-commit/kaimrdth/tui-train-times?style=flat-square)

Terminal countdown clock for NYC MTA subway arrivals. Modeled after the platform screens.

---

![tui-train-times in action](assets/ttt.gif)

---

## Setup

```bash
pip install nyct-gtfs rich
pip install pynput
```

Place `traintime.py` and `stations.json` in the same directory.

## Usage

```bash
python3 traintime.py
```

Type part of a station name, select from results, optionally filter by line. The clock launches and polls live MTA data every 30 seconds.

## Data

`stations.json` is generated from the GTFS static feed bundled with `nyct-gtfs`. To regenerate it:

```bash
python3 generate_stations.py
```

Covers all 499 NYC subway stations. Bullet colors use official MTA brand hex values.

## Stack

- [`nyct-gtfs`](https://github.com/Andrew-Dickinson/nyct-gtfs) for real-time feed parsing
- [`rich`](https://github.com/Textualize/rich) for terminal rendering