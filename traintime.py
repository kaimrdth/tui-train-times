import sys
import json
import time
import queue
import threading
import pathlib
from datetime import datetime
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.rule import Rule
from rich.align import Align
from rich.text import Text
from rich.prompt import Prompt
try:
    from pynput import keyboard as pynput_keyboard
    _HAVE_PYNPUT = True
except ImportError:
    _HAVE_PYNPUT = False

try:
    from nyct_gtfs import NYCTFeed
    _HAVE_MTA = True
except ImportError:
    _HAVE_MTA = False

# ── Theme ─────────────────────────────────────────────────────────────────────
BG        = "#1e2530"
TEXT      = "bright_white"
DIM_TEXT  = "#8899aa"
SEP       = "#2a3a4e"
ROW_LINES = 4

# ── Load station library ──────────────────────────────────────────────────────
_STATIONS_PATH = pathlib.Path(__file__).parent / "stations.json"

def load_stations() -> dict:
    if not _STATIONS_PATH.exists():
        return {}
    with open(_STATIONS_PATH) as f:
        return json.load(f)


# ── Station picker ────────────────────────────────────────────────────────────

def search_stations(stations: dict, query: str) -> list:
    q = query.strip().lower()
    return [(sid, data) for sid, data in stations.items() if q in data["name"].lower()]


def pick_station(stations: dict) -> tuple:
    console = Console()
    console.print(f"\n[bold bright_white]MTA Countdown Clock[/]\n", justify="center")
    console.print(f"[dim {DIM_TEXT}]Type part of a station name to search.[/]\n")

    while True:
        query = Prompt.ask("[bold white]Search station[/]").strip()
        if not query:
            continue

        results = search_stations(stations, query)

        if not results:
            console.print(f"[dim red]No stations found for '{query}'. Try again.[/]\n")
            continue

        display = results[:12]
        console.print()
        for i, (sid, data) in enumerate(display, 1):
            lines_str = "  ".join(
                f"[bold {data['colors'].get(l, {}).get('fg', 'white')} on {data['colors'].get(l, {}).get('bg', '#333')}] {l} [/]"
                for l in data["lines"]
            )
            console.print(f"  [dim]{i:>2}.[/]  {data['name']:<35} {lines_str}")

        if len(results) > 12:
            console.print(f"  [dim]... and {len(results) - 12} more. Refine your search.[/]")

        console.print()
        choice = Prompt.ask(f"[bold white]Select (1-{len(display)})[/]", default="1").strip()

        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(display)):
                raise ValueError
        except ValueError:
            console.print("[dim red]Invalid choice. Try again.[/]\n")
            continue

        stop_id, station = display[idx]
        available_lines  = station["lines"]

        if len(available_lines) == 1:
            selected_lines = available_lines
        else:
            console.print()
            lines_str = "  ".join(
                f"[bold {station['colors'].get(l, {}).get('fg', 'white')} on {station['colors'].get(l, {}).get('bg', '#333')}] {l} [/]"
                for l in available_lines
            )
            console.print(f"  Lines at [bold]{station['name']}[/]: {lines_str}")
            line_choice = Prompt.ask(
                "[bold white]Filter by line (or Enter for all)[/]", default=""
            ).strip().upper()

            if not line_choice:
                selected_lines = available_lines
            elif line_choice in available_lines:
                selected_lines = [line_choice]
            else:
                console.print(f"[dim red]'{line_choice}' doesn't serve this station. Showing all lines.[/]")
                selected_lines = available_lines

        return stop_id, station, selected_lines


# ── MTA data fetching ─────────────────────────────────────────────────────────

latest_arrivals = []

FEED_KEY_TO_LINE = {
    "gtfs":      "1",
    "gtfs-ace":  "A",
    "gtfs-bdfm": "B",
    "gtfs-g":    "G",
    "gtfs-jz":   "J",
    "gtfs-nqrw": "N",
    "gtfs-l":    "L",
    "gtfs-si":   "SI",
}

def fetch_mta_data_background(stop_id: str, station: dict, lines: list):
    global latest_arrivals
    feed_keys = sorted(set(station.get("feeds", [])))

    while True:
        try:
            arrivals = []
            for feed_key in feed_keys:
                feed_line = FEED_KEY_TO_LINE.get(feed_key)
                if not feed_line:
                    continue
                feed = NYCTFeed(feed_line)
                for line in lines:
                    for trip in feed.filter_trips(line_id=line):
                        for stop in trip.stop_time_updates:
                            if stop_id in stop.stop_id and stop.arrival:
                                diff = stop.arrival - datetime.now()
                                mins = int(diff.total_seconds() / 60)
                                if mins < 0:
                                    continue
                                dirn_key  = "N" if stop.stop_id.endswith("N") else "S"
                                direction = station["directions"][dirn_key]
                                terminal  = station["terminals"].get(line, {}).get(dirn_key, "")
                                arrivals.append({
                                    "line":      line,
                                    "direction": direction,
                                    "terminal":  terminal,
                                    "minutes":   mins,
                                })
            arrivals.sort(key=lambda x: x["minutes"])
            latest_arrivals = arrivals[:4]
        except Exception:
            pass
        time.sleep(30)


def demo_arrivals(station: dict, lines: list) -> list:
    t     = int(time.time())
    dirns = station.get("directions", {"N": "Uptown", "S": "Downtown"})
    terms = station.get("terminals", {})
    out   = []
    for i, offset in enumerate([3, 7, 12, 18]):
        line     = lines[i % len(lines)]
        dirn_key = "N" if i % 2 == 0 else "S"
        out.append({
            "line":      line,
            "direction": dirns[dirn_key],
            "terminal":  terms.get(line, {}).get(dirn_key, ""),
            "minutes":   max(0, offset - (t % (offset * 60)) // 60),
        })
    return out


# ── Rendering ─────────────────────────────────────────────────────────────────

def bullet(line: str, colors: dict) -> Text:
    c = colors.get(line, {"bg": "#333333", "fg": "white"})
    t = Text()
    t.append(f" {line} ", style=f"bold {c['fg']} on {c['bg']}")
    return t


def minutes_text(minutes: int, top_pad: int) -> Text:
    t   = Text(justify="right")
    pad = "\n" * top_pad
    if minutes == 0:
        t.append(pad)
        t.append("DUE", style="bold red blink")
    else:
        t.append(pad)
        t.append(f"{minutes}\n", style="bold bright_white")
        t.append("MIN", style=f"dim {DIM_TEXT}")
    return t


def render_row(arr: dict, idx: int, colors: dict) -> Table:
    line      = arr["line"]
    direction = arr["direction"]
    terminal  = arr["terminal"]
    minutes   = arr["minutes"]
    top_pad   = (ROW_LINES - 2) // 2

    prefix_width = 1 + len(str(idx)) + 1 + 2 + 1 + len(line) + 1 + 3

    left = Text()
    left.append("\n" * top_pad)
    left.append(f" {idx} ", style=f"dim {DIM_TEXT}")
    left.append("  ")
    left.append_text(bullet(line, colors))
    left.append(f"   {direction}\n", style="bold bright_white")
    left.append(" " * prefix_width + terminal, style=f"dim {DIM_TEXT}")

    right = minutes_text(minutes, top_pad)

    t = Table(show_header=False, box=None, expand=True, padding=(0, 3), show_edge=False)
    t.add_column("left",  ratio=1,  vertical="top")
    t.add_column("right", width=16, justify="right", vertical="top", no_wrap=True)
    t.add_row(left, right)
    return t


def render_flip_frame(arr: dict, idx: int, frame: int, total_frames: int, colors: dict) -> Table:
    if frame >= total_frames // 2:
        return render_row(arr, idx, colors)
    return _empty_row()


def _empty_row() -> Table:
    t = Table(show_header=False, box=None, expand=True, padding=(0, 3), show_edge=False)
    t.add_column("left",  ratio=1)
    t.add_column("right", width=16)
    t.add_row("\n" * ROW_LINES, "")
    return t


def _no_trains_row(station_name: str) -> Table:
    t = Table(show_header=False, box=None, expand=True, padding=(0, 2), show_edge=False)
    t.add_column("content", ratio=1, vertical="middle")
    t.add_row(f"\n\n[dim {DIM_TEXT}]No trains currently scheduled at {station_name}[/]\n\n")
    return t


# ── Keypress listener ─────────────────────────────────────────────────────────

_key_queue: queue.Queue = queue.Queue()

def _start_key_listener():
    """Start a pynput keyboard listener that pushes chars to _key_queue."""
    if not _HAVE_PYNPUT:
        return None

    def on_press(key):
        try:
            _key_queue.put(key.char)
        except AttributeError:
            pass

    listener = pynput_keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    return listener


# ── Main TUI loop ─────────────────────────────────────────────────────────────

def run_tui(stop_id: str, station: dict, lines: list):
    colors       = station.get("colors", {})
    station_name = station["name"].upper()
    demo_mode    = not _HAVE_MTA

    console = Console(style=f"on {BG}")
    console.clear()

    # Drain any stale keypresses from a previous run
    while not _key_queue.empty():
        _key_queue.get_nowait()

    listener = _start_key_listener()

    if not demo_mode:
        worker = threading.Thread(
            target=fetch_mta_data_background,
            args=(stop_id, station, lines),
            daemon=True,
        )
        worker.start()
        time.sleep(1.5)

    FLIP_FRAMES    = 8
    PAGE_DURATION  = 12
    flip_frame     = FLIP_FRAMES
    last_page_time = time.time()
    current_page   = 0
    flipping       = False
    flip_target    = None

    with Live(console=console, screen=True, refresh_per_second=8) as live:
        while True:
            arrivals = (demo_arrivals(station, lines) if demo_mode else latest_arrivals)[:4]

            now     = time.time()
            elapsed = now - last_page_time

            num_pages = max(1, (len(arrivals) + 1) // 2)

            if elapsed >= PAGE_DURATION and not flipping:
                next_page = (current_page + 1) % num_pages
                if next_page != current_page:
                    flipping       = True
                    flip_frame     = 0
                    flip_target    = next_page
                    last_page_time = now

            if flipping:
                flip_frame += 1
                if flip_frame >= FLIP_FRAMES:
                    flipping     = False
                    current_page = flip_target
                    flip_frame   = FLIP_FRAMES

            start      = current_page * 2
            page_slice = arrivals[start:start + 2]

            if not arrivals:
                row1 = _no_trains_row(station["name"])
                row2 = _empty_row()
            else:
                row1_arr = page_slice[0] if len(page_slice) > 0 else None
                row2_arr = page_slice[1] if len(page_slice) > 1 else None

                row1 = render_row(row1_arr, start + 1, colors) if row1_arr else _empty_row()

                if row2_arr:
                    if flipping:
                        row2 = render_flip_frame(row2_arr, start + 2, flip_frame, FLIP_FRAMES, colors)
                    else:
                        row2 = render_row(row2_arr, start + 2, colors)
                else:
                    row2 = _empty_row()

            header = Align.center(f"[bold {TEXT}]{station_name}[/]")
            footer = Align.right(f"[dim #3a4a5e]r — change station[/]  ")

            live.update(Group(
                header,
                Rule(style=SEP),
                row1,
                Rule(style=SEP),
                row2,
                footer,
            ))

            # Check for keypress
            try:
                key = _key_queue.get_nowait()
                if key == "r":
                    if listener: listener.stop()
                    return "back"
                elif key in ("q",):
                    if listener: listener.stop()
                    return "quit"
            except queue.Empty:
                pass

            time.sleep(0.125)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    stations = load_stations()

    if not stations:
        print("Error: stations.json not found. Place it in the same directory as this script.")
        raise SystemExit(1)

    while True:
        stop_id, station, lines = pick_station(stations)
        result = run_tui(stop_id, station, lines)
        if result == "quit":
            break
        # Drain any queued keypresses and flush stdin before re-entering picker
        time.sleep(0.1)
        while not _key_queue.empty():
            _key_queue.get_nowait()
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)