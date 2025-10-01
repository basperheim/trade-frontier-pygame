import json
import math
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import pygame

WIDTH, HEIGHT = 1400, 800
MAP_WIDTH = 620
NEWS_PANEL_HEIGHT = 120
PRICE_HISTORY_DAYS = 14
NET_WORTH_HISTORY_DAYS = 40
FPS = 60
BG_COLOR = (18, 24, 32)
CITY_COLOR = (93, 179, 255)
CITY_ACTIVE_COLOR = (255, 221, 89)
TEXT_COLOR = (230, 235, 245)
PANEL_COLOR = (28, 38, 52)
BUTTON_COLOR = (56, 76, 104)
BUTTON_HOVER = (88, 122, 167)
MESSAGE_COLOR = (179, 207, 255)

GOODS = [
    {"name": "Spices", "base": 180, "bulk": 1},
    {"name": "Silk", "base": 240, "bulk": 1},
    {"name": "Gems", "base": 420, "bulk": 1},
    {"name": "Tea", "base": 90, "bulk": 1},
    {"name": "Iron", "base": 120, "bulk": 2},
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class City:
    name: str
    position: Tuple[int, int]
    price_bias: Dict[str, float]
    charm: int
    seed: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.seed = sum(ord(char) for char in self.name) * 7919

    def prices_for_day(
        self,
        day: int,
        trends: Dict[str, float],
        event_boosts: Dict[str, float],
    ) -> Dict[str, int]:
        rng = random.Random(self.seed + day * 104729)
        prices = {}
        for good in GOODS:
            base = good["base"] * self.price_bias.get(good["name"], 1.0)
            trend = trends.get(good["name"], 1.0)
            event = event_boosts.get(good["name"], 1.0)
            demand = rng.uniform(0.85, 1.15)
            mood = rng.uniform(0.94, 1.08)
            price = int(base * trend * event * demand * mood)
            prices[good["name"]] = max(12, price // 3 * 3)
        return prices

    def travel_time_to(self, other: "City") -> int:
        dist = math.dist(self.position, other.position)
        return max(1, int(math.ceil(dist / 185)))

    def travel_cost_to(self, other: "City") -> int:
        time = self.travel_time_to(other)
        scenic = (self.charm + other.charm) / 80
        base_cost = 18
        scenic_discount = clamp(0.5 + scenic * 0.4, 0.45, 1.0)
        return max(12, int(base_cost * time * scenic_discount))


class TradeFrontier:
    def __init__(self, load_from_disk: bool = True) -> None:
        pygame.init()
        pygame.display.set_caption("Trade Frontier")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = self._load_font(24)
        self.small_font = self._load_font(18)
        self.heading_font = self._load_font(30, bold=True)
        self.large_font = self._load_font(44, bold=True)

        self.cities = self._build_cities()
        self.current_city: City = self.cities[0]
        self.day = 1
        self.max_days = 64
        self.money = 10_000
        self.cargo_capacity = 32
        self.cargo: Dict[str, int] = {good["name"]: 0 for good in GOODS}
        self.message = "Welcome to Trade Frontier. Click a city to travel!"
        self.game_over = False
        self.click_targets: List[Dict[str, object]] = []
        self.save_path = Path(__file__).with_name("savegame.json")
        self.scoreboard_path = Path(__file__).with_name("scoreboard.json")
        self._ensure_scoreboard_store()
        self.score_recorded = False

        self.market_trend: Dict[str, float] = {good["name"]: 1.0 for good in GOODS}
        self.trend_phase: Dict[str, float] = {good["name"]: 0.0 for good in GOODS}
        self.trend_velocity: Dict[str, float] = {good["name"]: 0.0 for good in GOODS}
        self.trend_offsets: Dict[str, float] = {
            good["name"]: random.Random(good["name"]).uniform(0, math.tau)
            for good in GOODS
        }
        self.trend_seeds: Dict[str, int] = {
            good["name"]: hash(good["name"]) & 0xFFFFFFFF
            for good in GOODS
        }
        self.news_seed: int = 0
        self.news_event: Dict[str, object] | None = None
        self.news_history: List[str] = []
        self.price_history: Dict[str, Dict[str, List[Tuple[int, int]]]] = {}
        self.net_worth_history: List[Tuple[int, int]] = []
        self.chart_options: List[str] = [good["name"] for good in GOODS] + ["Net Worth"]
        self.selected_chart_option: str = self.chart_options[0]

        if not (load_from_disk and self._load_state_if_exists()):
            self._init_new_charter()

    def _build_cities(self) -> List[City]:
        return [
            City("Harborlight", (110, 520), {"Spices": 1.1, "Tea": 0.9}, charm=54),
            City("Sunspire", (270, 150), {"Gems": 1.3, "Silk": 1.1}, charm=72),
            City("Verdant Vale", (480, 310), {"Tea": 1.4, "Iron": 0.8}, charm=64),
            City("Irondeep", (320, 520), {"Iron": 1.5, "Spices": 0.7}, charm=33),
            City("Azure Bay", (540, 120), {"Silk": 0.9, "Spices": 1.2}, charm=81),
            City("Emberfall", (170, 320), {"Gems": 1.2, "Iron": 1.1}, charm=58),
        ]

    def run(self) -> None:
        while True:
            self.clock.tick(FPS)
            self._handle_events()
            self._draw()
            if self.game_over:
                self._draw_game_over()
            pygame.display.flip()
            if self.game_over:
                # Let the overlay breathe but keep processing events
                pygame.time.wait(120)

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if self.game_over and event.key == pygame.K_r:
                    self._restart_game()
                if event.key == pygame.K_SPACE and not self.game_over:
                    self._rest_day()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.game_over:
                    self._handle_restart_click(event.pos)
                else:
                    self._handle_click(event.pos)

    def _handle_click(self, pos: Tuple[int, int]) -> None:
        for target in self.click_targets:
            rect = target["rect"]
            if rect.collidepoint(pos):
                action = target["type"]
                if action == "city":
                    self._travel_to(target["city"])
                elif action == "buy":
                    self._buy_good(target["good"])
                elif action == "sell":
                    self._sell_good(target["good"])
                elif action == "rest":
                    self._rest_day()
                elif action == "save":
                    self._manual_save()
                elif action == "restart":
                    self._restart_game()
                elif action == "chart_prev":
                    self._change_selected_metric(-1)
                elif action == "chart_next":
                    self._change_selected_metric(1)
                elif action == "upgrade":
                    self._upgrade_cargo_hold()
                return

    def _travel_to(self, city: City) -> None:
        if city == self.current_city:
            self.message = f"Already in {city.name}."
            return
        travel_time = self.current_city.travel_time_to(city)
        travel_cost = self.current_city.travel_cost_to(city)
        if travel_cost > self.money:
            self.message = "Not enough coin for that journey."
            return

        self.money -= travel_cost
        self.current_city = city
        headlines = self._progress_time(travel_time)
        if self.game_over:
            self._record_score()
            self._save_state()
            return

        event_text = self._travel_event(city)
        digest = self._news_digest(headlines)
        message = (
            f"Reached {city.name} in {travel_time} day{'s' if travel_time > 1 else ''}. "
            f"Paid {travel_cost} coin. {event_text}"
        )
        if digest:
            message = f"{message} {digest}"
        self.message = message
        self._save_state()

    def _travel_event(self, city: City) -> str:
        rng = random.Random(self.day * 92821 + city.seed)
        chance = rng.random()
        if chance < 0.1 and self.money > 0:
            toll = int(self.money * clamp(rng.uniform(0.08, 0.18), 0.05, 0.25))
            self.money -= toll
            return f"Skyway toll collectors relieved you of {toll} coin."
        if chance > 0.92:
            bonus = int(60 * rng.uniform(1.0, 2.2))
            self.money += bonus
            return f"You entertained nobles en route and earned {bonus} coin!"
        return rng.choice([
            "Markets whisper of shifting prices...",
            "Local guides share hidden shortcuts.",
            "The crew stays in good spirits.",
            "You collect rumors of distant shortages.",
        ])

    def _rest_day(self) -> None:
        if self.game_over:
            return
        headlines = self._progress_time(1)
        if self.game_over:
            self._record_score()
            self._save_state()
            return
        digest = self._news_digest(headlines)
        base_message = f"You spend a day networking in {self.current_city.name}."
        if digest:
            base_message = f"{base_message} {digest}"
        self.message = base_message
        self._save_state()

    def _check_game_over(self) -> None:
        if self.day > self.max_days:
            self.game_over = True
            self.message = "Your trading charter expires. Use Restart to begin anew."
            self._record_score()
            self._save_state()

    def _buy_good(self, good: str) -> None:
        price = self.prices[good]
        bulk = next(g["bulk"] for g in GOODS if g["name"] == good)
        cargo_load = sum(self.cargo[g["name"]] * g["bulk"] for g in GOODS)
        if cargo_load + bulk > self.cargo_capacity:
            self.message = "Cargo hold is full."
            return
        if price > self.money:
            self.message = "Not enough coin to buy."
            return
        self.money -= price
        self.cargo[good] += 1
        self.message = f"Purchased 1 crate of {good}."
        self._record_net_worth()
        self._save_state()

    def _sell_good(self, good: str) -> None:
        if self.cargo[good] <= 0:
            self.message = f"No {good} to sell."
            return
        price = self.prices[good]
        self.cargo[good] -= 1
        self.money += price
        self.message = f"Sold 1 crate of {good}."
        self._record_net_worth()
        self._save_state()

    def _manual_save(self) -> None:
        self.message = "Manifest logged. Charter saved."
        self._save_state()

    def _restart_game(self) -> None:
        self._delete_save()
        self._init_new_charter()

    def _handle_restart_click(self, pos: Tuple[int, int]) -> None:
        for target in self.click_targets:
            rect = target["rect"]
            if rect.collidepoint(pos) and target["type"] == "restart":
                self._restart_game()
                return

    def _progress_time(self, days: int) -> List[str]:
        headlines: List[str] = []
        for _ in range(days):
            self.day += 1
            self._update_market_trends()
            headline = self._update_news_cycle()
            if headline:
                headlines.append(headline)
        self._recalculate_prices()
        self._check_game_over()
        return headlines

    def _reset_market_state(self, rng: random.Random | None = None) -> None:
        source = rng or random.SystemRandom()
        for good in GOODS:
            name = good["name"]
            self.trend_phase[name] = source.uniform(0, math.tau)
            self.trend_velocity[name] = source.uniform(0.04, 0.09)
        self._update_market_trends(initial=True)

    def _update_market_trends(self, *, initial: bool = False) -> None:
        for good in GOODS:
            name = good["name"]
            if not initial:
                noise = self._trend_noise(name, self.day)
                target_velocity = 0.055 + noise * 0.02
                self.trend_velocity[name] = (
                    0.88 * self.trend_velocity[name] + 0.12 * target_velocity
                )
                self.trend_phase[name] += self.trend_velocity[name]
            fast_wave = math.sin(self.trend_phase[name])
            slow_wave = math.sin(self.trend_phase[name] * 0.45 + self.trend_offsets[name])
            combined = 0.65 * fast_wave + 0.35 * slow_wave
            self.market_trend[name] = 1.0 + combined * 0.18

    def _trend_noise(self, good: str, day: int) -> float:
        rng = random.Random(self.trend_seeds[good] + day * 1931)
        return rng.uniform(-1.0, 1.0)

    def _event_price_boost(self) -> Dict[str, float]:
        if self.news_event and self.day <= int(self.news_event.get("expires_on", 0)):
            return {self.news_event["good"]: float(self.news_event["modifier"])}
        return {}

    def _recalculate_prices(self) -> None:
        self.prices = self.current_city.prices_for_day(
            self.day, self.market_trend, self._event_price_boost()
        )
        self._record_price_snapshot()

    def _news_ticker(self) -> str:
        if self.news_event and self.day <= int(self.news_event.get("expires_on", 0)):
            remaining = int(self.news_event["expires_on"]) - self.day + 1
            summary = self.news_event.get("summary", "")
            return f"News: {summary} ({remaining}d)"
        return ""

    def _news_digest(self, headlines: List[str]) -> str:
        parts = [headline for headline in headlines if headline]
        ticker = self._news_ticker()
        if ticker:
            parts.append(ticker)
            self._record_headline(ticker)
        return " ".join(parts)

    def _record_headline(self, headline: str | None) -> None:
        if not headline:
            return
        self.news_history.append(f"Day {self.day}: {headline}")
        if len(self.news_history) > 24:
            del self.news_history[0]

    def _recent_headlines(self, *, max_entries: int) -> List[str]:
        return list(self.news_history[-max_entries:][::-1])

    def _wrap_text(self, text: str, width: int) -> List[str]:
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if self.small_font.size(candidate)[0] <= width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _record_price_snapshot(self) -> None:
        city_history = self.price_history.setdefault(self.current_city.name, {})
        for good in GOODS:
            name = good["name"]
            series = city_history.setdefault(name, [])
            if series and series[-1][0] == self.day:
                series[-1] = (self.day, self.prices[name])
            else:
                series.append((self.day, self.prices[name]))
            if len(series) > PRICE_HISTORY_DAYS:
                del series[0]
        self._record_net_worth()

    def _record_net_worth(self) -> None:
        net = self._current_net_worth()
        if self.net_worth_history and self.net_worth_history[-1][0] == self.day:
            self.net_worth_history[-1] = (self.day, net)
        else:
            self.net_worth_history.append((self.day, net))
        if len(self.net_worth_history) > NET_WORTH_HISTORY_DAYS:
            del self.net_worth_history[0]
        if self.game_over:
            self._record_score()

    def _current_net_worth(self) -> int:
        cargo_value = sum(self.cargo[item["name"]] * self.prices[item["name"]] for item in GOODS)
        return self.money + cargo_value

    def _recent_metric_data(self, option: str) -> List[Tuple[int, int]]:
        if option == "Net Worth":
            data = list(self.net_worth_history)
        else:
            city_history = self.price_history.get(self.current_city.name, {})
            data = list(city_history.get(option, []))

        data.sort(key=lambda item: item[0])
        if len(data) >= 2:
            return data

        baseline_val = self._baseline_value(option)
        if not data:
            day0 = max(1, self.day - 1)
            return [(day0, baseline_val), (self.day, baseline_val)]

        day_single, value_single = data[0]
        baseline_day = day_single - 1 if day_single > 1 else max(0, day_single - 1)
        if baseline_day == day_single:
            baseline_day = day_single - 1
        baseline_entry = (baseline_day, baseline_val)
        return [baseline_entry, (day_single, value_single)]

    def _baseline_value(self, option: str) -> int:
        if option == "Net Worth":
            return self._current_net_worth()
        for good in GOODS:
            if good["name"] == option:
                base_price = good["base"] * self.current_city.price_bias.get(option, 1.0)
                return int(base_price)
        return self._current_net_worth()

    def _change_selected_metric(self, delta: int) -> None:
        if self.selected_chart_option not in self.chart_options:
            self.selected_chart_option = self.chart_options[0]
        idx = self.chart_options.index(self.selected_chart_option)
        idx = (idx + delta) % len(self.chart_options)
        self.selected_chart_option = self.chart_options[idx]
        self.message = f"Reviewing trend for {self.selected_chart_option}."

    def _upgrade_cargo_hold(self) -> None:
        upgrade_cost = 260
        capacity_step = 4
        if self.money < upgrade_cost:
            self.message = "Need more coin to upgrade cargo hold."
            return
        self.money -= upgrade_cost
        self.cargo_capacity += capacity_step
        self.message = (
            f"Cargo hold expanded by {capacity_step}. New capacity: {self.cargo_capacity}."
        )
        self._record_net_worth()
        self._save_state()

    def _record_score(self) -> None:
        if self.score_recorded:
            return
        try:
            if self.scoreboard_path.exists():
                with self.scoreboard_path.open("r", encoding="utf-8") as handle:
                    board = json.load(handle)
            else:
                board = {"entries": []}
        except (OSError, json.JSONDecodeError):
            board = {"entries": []}

        entry = {
            "timestamp": time.time(),
            "day": self.day,
            "city": self.current_city.name,
            "net_worth": self._current_net_worth(),
            "money": self.money,
            "cargo": dict(self.cargo),
        }
        board.setdefault("entries", []).append(entry)
        board["entries"] = sorted(
            board["entries"], key=lambda item: item.get("net_worth", 0), reverse=True
        )[:25]
        board["updated_at"] = time.time()

        try:
            with self.scoreboard_path.open("w", encoding="utf-8") as handle:
                json.dump(board, handle, indent=2)
        except OSError:
            pass
        else:
            self.score_recorded = True

    def _update_news_cycle(self) -> str | None:
        headline: str | None = None
        if self.news_event and self.day > int(self.news_event.get("expires_on", 0)):
            conclusion = self.news_event.get("conclusion", "Markets stabilize.")
            good = self.news_event.get("good", "Goods")
            headline = f"News fades: {good} {conclusion}"
            self.news_event = None
            self._record_headline(headline)

        if self.news_event is None:
            rng = random.Random(self.news_seed + self.day * 6151)
            if rng.random() < 0.12:
                event = self._generate_news_event(rng)
                event_duration = event.pop("duration")
                event["expires_on"] = self.day + event_duration - 1
                self.news_event = event
                headline = event["headline"]
                self._record_headline(headline)
        return headline

    def _generate_news_event(self, rng: random.Random) -> Dict[str, object]:
        good_data = rng.choice(GOODS)
        good = good_data["name"]
        bullish = rng.random() < 0.5
        magnitude = rng.uniform(0.27, 0.48)
        duration = rng.randint(3, 5)
        city = rng.choice(self.cities).name
        if bullish:
            modifier = 1.0 + magnitude
            headline = (
                f"News: {city} festival sends {good} demand surging (+{int(magnitude * 100)}%)."
            )
            summary = f"{good} boom after {city} celebrations"
            conclusion = "boom calms"
        else:
            modifier = max(0.45, 1.0 - magnitude)
            headline = (
                f"News: {city} bottlenecks crash {good} prices (-{int(magnitude * 100)}%)."
            )
            summary = f"{good} glut from {city} overstock"
            conclusion = "slump eases"

        return {
            "good": good,
            "modifier": modifier,
            "summary": summary,
            "headline": headline,
            "conclusion": conclusion,
            "duration": duration,
        }

    def _draw(self) -> None:
        self.click_targets = []
        self.screen.fill(BG_COLOR)
        self._draw_map()
        self._draw_panel()

    def _init_new_charter(self) -> None:
        self.current_city = self.cities[0]
        self.day = 1
        self.money = 10_000
        self.cargo_capacity = 32
        self.cargo = {good["name"]: 0 for good in GOODS}
        self.game_over = False
        self.message = "Welcome to Trade Frontier. Click a city to travel!"
        self.news_seed = random.SystemRandom().randrange(1, 1_000_000_000)
        self.news_event = None
        self.news_history = []
        self.price_history = {}
        self.net_worth_history = []
        self.score_recorded = False
        self._reset_market_state()
        self._recalculate_prices()
        self._save_state()

    def _load_state_if_exists(self) -> bool:
        if not self.save_path.exists():
            return False
        try:
            with self.save_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False

        city_lookup = {city.name: city for city in self.cities}
        saved_city = city_lookup.get(data.get("city"))
        if saved_city is None:
            return False

        self.current_city = saved_city
        self.day = int(data.get("day", 1))
        self.money = int(data.get("money", 900))
        self.cargo_capacity = int(data.get("cargo_capacity", self.cargo_capacity))
        saved_cargo = data.get("cargo", {})
        self.cargo = {
            good["name"]: int(saved_cargo.get(good["name"], 0)) for good in GOODS
        }
        self.game_over = bool(data.get("game_over", False))
        default_message = f"Resumed charter in {self.current_city.name}."
        self.message = data.get("message", default_message)
        saved_phase = data.get("trend_phase", {})
        for name, value in saved_phase.items():
            if name in self.trend_phase:
                self.trend_phase[name] = float(value)

        saved_velocity = data.get("trend_velocity", {})
        for name, value in saved_velocity.items():
            if name in self.trend_velocity:
                self.trend_velocity[name] = float(value)

        saved_market = data.get("market_trend", {})
        for name, value in saved_market.items():
            if name in self.market_trend:
                self.market_trend[name] = float(value)

        self.news_seed = int(
            data.get("news_seed", random.SystemRandom().randrange(1, 1_000_000_000))
        )
        self.news_event = data.get("news_event")
        if self.news_event and self.day > int(self.news_event.get("expires_on", 0)):
            self.news_event = None

        self.news_history = data.get("news_history", [])[-12:]
        saved_prices = data.get("price_history", {})
        self.price_history = {
            city: {
                good: [(int(day), int(price)) for day, price in entries][-PRICE_HISTORY_DAYS:]
                for good, entries in goods.items()
            }
            for city, goods in saved_prices.items()
        }
        self.net_worth_history = [
            (int(day), int(value)) for day, value in data.get("net_worth_history", [])
        ][-NET_WORTH_HISTORY_DAYS:]
        self.selected_chart_option = data.get(
            "selected_chart_option", self.selected_chart_option
        )
        if self.selected_chart_option not in self.chart_options:
            self.selected_chart_option = self.chart_options[0]
        self.score_recorded = bool(data.get("score_recorded", False))

        self._update_market_trends(initial=True)
        self._recalculate_prices()
        if self.game_over and not self.score_recorded:
            self._record_score()
        return True

    def _save_state(self) -> None:
        payload = {
            "day": self.day,
            "money": self.money,
            "cargo": self.cargo,
            "cargo_capacity": self.cargo_capacity,
            "city": self.current_city.name,
            "game_over": self.game_over,
            "message": self.message,
            "market_trend": self.market_trend,
            "trend_phase": self.trend_phase,
            "trend_velocity": self.trend_velocity,
            "news_seed": self.news_seed,
            "news_event": self.news_event,
            "news_history": self.news_history[-12:],
            "price_history": self.price_history,
            "net_worth_history": self.net_worth_history[-NET_WORTH_HISTORY_DAYS:],
            "selected_chart_option": self.selected_chart_option,
            "score_recorded": self.score_recorded,
        }
        try:
            with self.save_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except OSError:
            pass

    def _delete_save(self) -> None:
        try:
            self.save_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def _ensure_scoreboard_store(self) -> None:
        if self.scoreboard_path.exists():
            return
        payload = {"entries": [], "updated_at": time.time()}
        try:
            with self.scoreboard_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except OSError:
            pass

    def _load_font(self, size: int, *, bold: bool = False) -> pygame.font.Font:
        preferred = [
            "avenir next",
            "gill sans",
            "source sans pro",
            "trebuchet ms",
            "arial",
            "dejavu sans",
        ]
        path = pygame.font.match_font(preferred, bold=bold)
        font = pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
        if bold and not font.get_bold():
            font.set_bold(True)
        if hasattr(font, "set_hinting") and hasattr(pygame.font, "HINTING_LIGHT"):
            font.set_hinting(pygame.font.HINTING_LIGHT)
        return font

    def _draw_map(self) -> None:
        pygame.draw.rect(self.screen, (11, 16, 23), pygame.Rect(0, 0, MAP_WIDTH, HEIGHT))
        for city in self.cities:
            color = CITY_ACTIVE_COLOR if city == self.current_city else CITY_COLOR
            pygame.draw.circle(self.screen, color, city.position, 16)
            name_surface = self.small_font.render(city.name, True, TEXT_COLOR)
            name_rect = name_surface.get_rect(center=(city.position[0], city.position[1] - 26))
            self.screen.blit(name_surface, name_rect)
            info_surface = self.small_font.render(f"Charm {city.charm}", True, (115, 148, 186))
            info_rect = info_surface.get_rect(center=(city.position[0], city.position[1] + 26))
            self.screen.blit(info_surface, info_rect)

            target_rect = pygame.Rect(city.position[0] - 18, city.position[1] - 18, 36, 36)
            self.click_targets.append({"rect": target_rect, "type": "city", "city": city})

        footer_rect = pygame.Rect(0, HEIGHT - NEWS_PANEL_HEIGHT, MAP_WIDTH, NEWS_PANEL_HEIGHT)
        pygame.draw.rect(self.screen, (42, 58, 78), footer_rect)
        voyage_text = f"Day {self.day}/{self.max_days}  //  {self.current_city.name}"
        voyage_surface = self.font.render(voyage_text, True, TEXT_COLOR)
        self.screen.blit(voyage_surface, (16, HEIGHT - NEWS_PANEL_HEIGHT + 12))

        message_surface = self.small_font.render(self.message, True, MESSAGE_COLOR)
        self.screen.blit(message_surface, (16, HEIGHT - NEWS_PANEL_HEIGHT + 48))

        advice = self.small_font.render(
            "SPACE: Stay a day | R or panel button to restart",
            True,
            (138, 168, 210),
        )
        self.screen.blit(advice, (16, HEIGHT - 32))

    def _draw_panel(self) -> None:
        panel_rect = pygame.Rect(MAP_WIDTH, 0, WIDTH - MAP_WIDTH, HEIGHT)
        pygame.draw.rect(self.screen, PANEL_COLOR, panel_rect)

        row_y = 24
        row_x = MAP_WIDTH + 24
        title = self.heading_font.render("Manifest", True, TEXT_COLOR)
        title_rect = title.get_rect(topleft=(row_x, row_y))
        self.screen.blit(title, title_rect)

        info_x = title_rect.right + 24
        info_y = row_y + max(0, (title_rect.height - self.small_font.get_height()) // 2)
        net_worth = self._current_net_worth()
        info_texts = [
            self.small_font.render(f"Coin: {self.money}", True, TEXT_COLOR),
            self.small_font.render(
                f"Cargo: {sum(self.cargo[g['name']] * g['bulk'] for g in GOODS)}/{self.cargo_capacity}",
                True,
                TEXT_COLOR,
            ),
            self.small_font.render(f"Net Worth: {net_worth}", True, CITY_ACTIVE_COLOR),
        ]
        spacing = 22
        for surface in info_texts:
            self.screen.blit(surface, (info_x, info_y))
            info_x += surface.get_width() + spacing

        list_top = title_rect.bottom + 30
        self.screen.blit(self.font.render("Marketplace", True, TEXT_COLOR), (MAP_WIDTH + 24, list_top))
        header = self.small_font.render("Good", True, (164, 192, 228))
        header_y = list_top + 32
        self.screen.blit(header, (MAP_WIDTH + 24, header_y))
        header_price = self.small_font.render("Price", True, (164, 192, 228))
        self.screen.blit(header_price, (MAP_WIDTH + 140, header_y))
        header_hold = self.small_font.render("Hold", True, (164, 192, 228))
        self.screen.blit(header_hold, (MAP_WIDTH + 220, header_y))

        y = header_y + 28
        mouse_pos = pygame.mouse.get_pos()
        for good in GOODS:
            name = good["name"]
            price = self.prices[name]
            quantity = self.cargo[name]

            name_surface = self.small_font.render(name, True, TEXT_COLOR)
            self.screen.blit(name_surface, (MAP_WIDTH + 24, y))

            price_surface = self.small_font.render(str(price), True, TEXT_COLOR)
            self.screen.blit(price_surface, (MAP_WIDTH + 140, y))

            qty_surface = self.small_font.render(str(quantity), True, TEXT_COLOR)
            self.screen.blit(qty_surface, (MAP_WIDTH + 220, y))

            buy_rect = pygame.Rect(MAP_WIDTH + 266, y - 4, 72, 24)
            sell_rect = pygame.Rect(MAP_WIDTH + 344, y - 4, 72, 24)

            self._draw_button(buy_rect, "Buy", mouse_pos)
            self._draw_button(sell_rect, "Sell", mouse_pos)

            self.click_targets.append({"rect": buy_rect, "type": "buy", "good": name})
            self.click_targets.append({"rect": sell_rect, "type": "sell", "good": name})

            y += 44

        panel_width = WIDTH - MAP_WIDTH - 48
        chart_rect = pygame.Rect(MAP_WIDTH + 24, y + 16, panel_width, 180)
        self._draw_price_chart(chart_rect)

        news_rect = pygame.Rect(
            MAP_WIDTH + 24, chart_rect.bottom + 16, panel_width, 80
        )
        self._draw_news_panel(news_rect)

        button_top = news_rect.bottom + 16
        button_height = 42
        button_width = (panel_width - 12) // 2
        rest_rect = pygame.Rect(MAP_WIDTH + 24, button_top, button_width, button_height)
        upgrade_rect = pygame.Rect(
            rest_rect.right + 12, button_top, button_width, button_height
        )
        save_rect = pygame.Rect(
            MAP_WIDTH + 24, button_top + button_height + 12, button_width, button_height
        )
        restart_rect = pygame.Rect(
            save_rect.right + 12,
            button_top + button_height + 12,
            button_width,
            button_height,
        )

        self._draw_button(rest_rect, "Spend a day networking", mouse_pos)
        self._draw_button(upgrade_rect, "Upgrade cargo hold (+4 for 260 coin)", mouse_pos)
        self._draw_button(save_rect, "Save progress", mouse_pos)
        self._draw_button(restart_rect, "Restart charter", mouse_pos)

        self.click_targets.append({"rect": rest_rect, "type": "rest"})
        self.click_targets.append({"rect": upgrade_rect, "type": "upgrade"})
        self.click_targets.append({"rect": save_rect, "type": "save"})
        self.click_targets.append({"rect": restart_rect, "type": "restart"})

    def _draw_news_panel(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, (32, 46, 64), rect, border_radius=10)
        pygame.draw.rect(self.screen, (58, 82, 112), rect, width=2, border_radius=10)

        title = self.small_font.render("Newswire", True, TEXT_COLOR)
        self.screen.blit(title, (rect.x + 14, rect.y + 10))

        lines = self._recent_headlines(max_entries=2)
        if not lines:
            placeholder = self.small_font.render(
                "Markets quiet. Awaiting fresh rumors...", True, MESSAGE_COLOR
            )
            self.screen.blit(placeholder, (rect.x + 12, rect.y + 42))
            return

        y = rect.y + 36
        for headline in lines:
            wrapped = self._wrap_text(headline, rect.width - 24)
            for segment in wrapped:
                line_surface = self.small_font.render(segment, True, MESSAGE_COLOR)
                self.screen.blit(line_surface, (rect.x + 12, y))
                y += 18
            y += 4

    def _draw_price_chart(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, (30, 42, 58), rect, border_radius=10)
        pygame.draw.rect(self.screen, (64, 88, 120), rect, width=2, border_radius=10)

        title = self.small_font.render("Price Trends", True, TEXT_COLOR)
        self.screen.blit(title, (rect.x + 14, rect.y + 10))

        selector_rect = pygame.Rect(rect.right - 170, rect.y + 8, 150, 28)
        pygame.draw.rect(self.screen, BUTTON_COLOR, selector_rect, border_radius=6)
        pygame.draw.rect(self.screen, (16, 22, 30), selector_rect, width=2, border_radius=6)
        selected_label = self.small_font.render(self.selected_chart_option, True, TEXT_COLOR)
        label_rect = selected_label.get_rect(center=selector_rect.center)
        self.screen.blit(selected_label, label_rect)

        prev_rect = pygame.Rect(selector_rect.x - 32, selector_rect.y, 28, selector_rect.height)
        next_rect = pygame.Rect(selector_rect.right + 4, selector_rect.y, 28, selector_rect.height)
        mouse_pos = pygame.mouse.get_pos()
        self._draw_button(prev_rect, "<", mouse_pos, font=self.small_font)
        self._draw_button(next_rect, ">", mouse_pos, font=self.small_font)
        self.click_targets.append({"rect": prev_rect, "type": "chart_prev"})
        self.click_targets.append({"rect": next_rect, "type": "chart_next"})

        data = self._recent_metric_data(self.selected_chart_option)
        if len(data) < 2:
            notice = self.small_font.render("Collect more data to chart trends.", True, MESSAGE_COLOR)
            self.screen.blit(notice, (rect.x + 18, rect.y + 60))
            return

        plot_area = pygame.Rect(rect.x + 16, rect.y + 46, rect.width - 32, rect.height - 62)
        pygame.draw.rect(self.screen, (20, 28, 40), plot_area)

        values = [price for _, price in data]
        days = [day for day, _ in data]
        min_val = min(values)
        max_val = max(values)
        if min_val == max_val:
            min_val -= 1
            max_val += 1
        span = max_val - min_val

        points = []
        for idx, (day, price) in enumerate(data):
            x = plot_area.x + (plot_area.width * idx) / (len(data) - 1)
            y = plot_area.bottom - ((price - min_val) / span) * plot_area.height
            points.append((int(x), int(y)))

        pygame.draw.lines(self.screen, CITY_ACTIVE_COLOR, False, points, 3)
        for point in points:
            pygame.draw.circle(self.screen, (250, 224, 120), point, 4)

        caption = self.small_font.render(
            f"Last {len(data)} entries for {self.selected_chart_option}", True, (164, 192, 228)
        )
        self.screen.blit(caption, (rect.x + 18, rect.bottom - 24))

    def _draw_button(
        self,
        rect: pygame.Rect,
        label: str,
        mouse_pos: Tuple[int, int],
        *,
        font: pygame.font.Font | None = None,
    ) -> None:
        color = BUTTON_HOVER if rect.collidepoint(mouse_pos) else BUTTON_COLOR
        pygame.draw.rect(self.screen, color, rect, border_radius=6)
        pygame.draw.rect(self.screen, (16, 22, 30), rect, width=2, border_radius=6)
        font_obj = font or self.small_font
        text_surface = font_obj.render(label, True, TEXT_COLOR)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    def _draw_game_over(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 8, 12, 210))
        self.screen.blit(overlay, (0, 0))

        box_rect = pygame.Rect(0, 0, 680, 360)
        box_rect.center = (WIDTH // 2, HEIGHT // 2)
        pygame.draw.rect(self.screen, (36, 48, 66), box_rect, border_radius=18)
        pygame.draw.rect(self.screen, (78, 102, 136), box_rect, width=3, border_radius=18)

        center_x = box_rect.centerx
        y = box_rect.top + 36

        title = self.large_font.render("Charter Complete", True, CITY_ACTIVE_COLOR)
        self.screen.blit(title, title.get_rect(center=(center_x, y)))

        y += 70
        profit_text = self.font.render(f"Days Traveled: {self.day - 1}", True, TEXT_COLOR)
        self.screen.blit(profit_text, profit_text.get_rect(center=(center_x, y)))

        y += 36
        final_net = self._current_net_worth()
        fortune_text = self.font.render(f"Final Fortune: {final_net} coin", True, TEXT_COLOR)
        self.screen.blit(fortune_text, fortune_text.get_rect(center=(center_x, y)))

        y += 32
        cargo_stats = ", ".join(
            f"{item['name']}:{self.cargo[item['name']]}" for item in GOODS
        )
        cargo_surface = self.small_font.render(
            f"Cargo on hand: {cargo_stats}", True, MESSAGE_COLOR
        )
        self.screen.blit(cargo_surface, cargo_surface.get_rect(center=(center_x, y)))

        y += 48
        prompt = self.small_font.render(
            "Press R or click Restart to begin a new charter.", True, TEXT_COLOR
        )
        self.screen.blit(prompt, prompt.get_rect(center=(center_x, y)))


def main() -> None:
    game = TradeFrontier()
    game.run()


if __name__ == "__main__":
    main()
