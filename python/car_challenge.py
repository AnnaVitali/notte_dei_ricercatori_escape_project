"""Timing and CSV storage for the car challenge (no hardware dependencies)."""
import csv
import math
import time
from datetime import datetime, timezone
from pathlib import Path

RESULTS_FILE = Path(__file__).resolve().with_name("car_rankings.csv")
FIELDS = ("finished_at", "player", "elapsed_seconds", "path", "path_cost")
# Guard weights from minizinc/escape.dzn, indexed by the one-based node number.
NODE_COSTS = (0, 8, 3, 5, 0, 3, 9, 8, 0, 4, 0, 0, 10, 8, 14, 8)
MAP_EDGES = (
    (1, 2), (1, 10), (2, 3), (2, 7), (3, 4), (3, 8), (3, 11),
    (4, 5), (4, 8), (4, 16), (5, 16), (6, 10), (6, 11),
    (7, 8), (7, 12), (8, 12), (9, 15), (9, 16), (11, 14),
    (12, 13), (12, 14), (13, 15), (13, 16), (14, 15),
)


class Challenge:
    def __init__(self, clock=time.perf_counter, neighbours=None):
        self.clock = clock
        if neighbours is None:
            neighbours = {node: set() for node in range(1, 17)}
            for first, last in MAP_EDGES:
                neighbours[first].add(last)
                neighbours[last].add(first)
        self.neighbours = neighbours
        self.reset()

    def reset(self):
        self.path = [1]
        self.started = None
        self.finished = None
        self.player = ""

    @property
    def elapsed(self):
        if self.started is None:
            return 0.0
        return (self.finished if self.finished is not None else self.clock()) - self.started

    def move(self, node, player):
        if self.finished is not None or node == self.path[-1]:
            return
        if node in self.path:
            raise ValueError("You cannot return to a visited node.")
        if node not in self.neighbours[self.path[-1]]:
            raise ValueError("Choose a neighbouring node connected by a road.")
        self.start(player)
        self.path.append(node)

    def start(self, player):
        """Start on first physical drive or first recorded node move."""
        if self.started is None:
            self.player = player.strip() or "Anonymous"
            self.started = self.clock()

    @property
    def available_moves(self):
        if self.finished is not None or self.path[-1] == 9:
            return []
        return sorted(self.neighbours[self.path[-1]] - set(self.path))

    def stop(self):
        if self.started is not None and self.finished is None:
            self.finished = self.clock()

    def result(self):
        if self.finished is None or self.path[-1] != 9:
            raise ValueError("Only completed runs can be saved")
        path_cost = sum(NODE_COSTS[node - 1] for node in self.path)
        return dict(finished_at=datetime.now(timezone.utc).isoformat(),
                    player=self.player, elapsed_seconds=f"{self.elapsed:.6f}",
                    path=" -> ".join(map(str, self.path)), path_cost=path_cost)


def _path_cost(path):
    try:
        nodes = [int(node.strip()) for node in path.split("->")]
        if not nodes or any(node < 1 or node > len(NODE_COSTS) for node in nodes):
            raise ValueError
        return sum(NODE_COSTS[node - 1] for node in nodes)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid path in ranking CSV") from None


def load_results(filename=RESULTS_FILE):
    filename = Path(filename)
    if not filename.exists():
        return []
    # utf-8-sig accepts normal UTF-8 and Excel-generated UTF-8 CSVs with a BOM.
    with filename.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        columns = tuple(reader.fieldnames or ())
        legacy_columns = FIELDS[:-1]
        if columns not in (FIELDS, legacy_columns):
            raise ValueError("Unexpected ranking CSV columns")
        rows = list(reader)
    for row in rows:
        seconds = float(row["elapsed_seconds"])
        required = FIELDS if columns == FIELDS else legacy_columns
        if (not math.isfinite(seconds) or seconds < 0 or
                any(row.get(key) is None for key in required)):
            raise ValueError("Invalid ranking CSV row")
        if columns == legacy_columns:
            row["path_cost"] = _path_cost(row["path"])
        else:
            cost = int(row["path_cost"])
            if cost < 0:
                raise ValueError("Invalid ranking CSV row")
            row["path_cost"] = cost
    return sorted(rows, key=lambda row: (int(row["path_cost"]),
                                         float(row["elapsed_seconds"])))


def save_result(result, filename=RESULTS_FILE):
    filename = Path(filename)
    previous = load_results(filename)  # Do not append to an incompatible or damaged CSV.
    needs_header = not filename.exists()
    # Rewrite legacy files with the new column while retaining their old results.
    rewrite = False
    if filename.exists() and previous:
        with filename.open(newline="", encoding="utf-8-sig") as stream:
            rewrite = tuple(csv.DictReader(stream).fieldnames or ()) == FIELDS[:-1]
    if rewrite:
        filename.unlink()
    with filename.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        if needs_header:
            writer.writeheader()
        if rewrite:
            writer.writerows(previous)
        writer.writerow(result)
