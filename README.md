# Trade Frontier

**Trade Frontier** is a Pygame demo where you travel between port cities, buy and sell goods, and try to build your fortune before your trading charter expires. Each city has its own quirks, biases, and travel costs. Markets fluctuate daily with trends, random events, and news headlines that shape prices.

Your goal: finish the charter with the highest **net worth** possible.

---

## Features

- Six unique port cities, each with charm and price biases
- Dynamic market system with short-term trends and long-term waves
- Randomized news events that boost or crash goods prices
- Cargo management and ship upgrades
- Travel costs and scenic discounts based on city charm
- Save/load support with JSON state files
- Scoreboard to track your best fortunes
- In-game charts showing price and net worth history

---

## Requirements

- Python **3.9+**
- [Pygame](https://www.pygame.org/news) (>= 2.5.0)

You can install dependencies using pip:

```bash
pip install -r requirements.txt
```

---

## Running the Game

Clone or download the repository, then run:

```bash
python trade_frontier.py
```

The game window will open at **1400x800** resolution.

---

## How to Play

- **Click on a city** to travel. Travel consumes money and days.
- **Buy/Sell goods** in each marketplace to profit from price differences.
- **Press SPACE** (or use the panel button) to stay a day in your current city.
- **Upgrade cargo hold** to expand carrying capacity (+4 per upgrade).
- **Monitor trends** in the chart panel to anticipate future prices.
- **Save progress** anytime with the save button.
- The charter lasts **64 days** — when time runs out, your score is recorded.

---

## Controls

- **Mouse**: interact with cities, buttons, and UI
- **SPACE**: stay one day
- **R**: restart game (after it ends)
- **ESC**: quit

---

## Save Files

- `savegame.json`: stores your current run (auto-saved frequently)
- `scoreboard.json`: tracks your top fortunes (keeps the 25 best entries)

---

## Development Notes

- All core logic is in [`trade_frontier.py`](trade_frontier.py).
- Graphics are drawn with Pygame primitives (no image assets required).
- Price and net worth histories are capped at configurable lengths (`PRICE_HISTORY_DAYS` and `NET_WORTH_HISTORY_DAYS`).
- Runs at 60 FPS.

---

## License

This project is provided as a demo/game prototype. You're free to modify, extend, or repurpose it for your own projects.
