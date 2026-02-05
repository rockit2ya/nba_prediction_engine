## 🏀 NBA Prediction Engine

A high-performance Python-based analytical tool designed to identify betting edges in the NBA. This engine moves beyond basic win/loss records, utilizing the **Four-Factor Model** and a proprietary **Fatigue Adjuster** to account for the unique rigors of the NBA schedule.

---

## 🚀 Quick Start: Environment Setup

Follow these steps to get the engine running on your local machine using **Python 3.14.2**.

### 1. Clone & Navigate

```bash
git clone https://github.com/your-username/nba_prediction_engine.git
cd nba_prediction_engine

```

### 2. Create the Virtual Environment

To keep this project isolated from your NFL engine:

```bash
python3 -m venv nba_predict

```

### 3. Activate the Environment

* **macOS/Linux:**
```bash
source nba_predict/bin/activate

```


* **Windows:**
```bash
nba_predict\Scripts\activate

```



### 4. Install Dependencies

```bash
pip install -r requirements.txt

```

---

## 🧠 Core Methodology

The engine calculates a "Fair Line" by analyzing two primary data layers:

### The Four-Factor Model

We weigh the four most critical components of basketball success:

1. **Effective Field Goal % (eFG%)** - Shooting efficiency.
2. **Turnover % (TOV%)** - Ball security.
3. **Offensive Rebound % (ORB%)** - Second-chance points.
4. **Free Throw Rate (FT Rate)** - Ability to draw fouls.

### The Fatigue Adjuster (Rest Advantage)

In the NBA, schedule-driven fatigue is a quantifiable edge. The engine applies the following penalties to a team’s Offensive Rating:

* **Back-to-Back (B2B):**  points.
* **3rd Game in 4 Nights:**  points.
* **Travel Penalty:** Applied based on flight mileage between cities.

---

## 🛠️ Usage

To run the interactive selection interface:

```bash
python nba_engine_ui.py

```

1. **Select Game:** Choose a Game ID from the daily slate (e.g., `G7`).
2. **Input Market Spread:** Enter the current spread from your sportsbook.
3. **Analyze:** The engine will output the **Model Line** vs. **Market Line** and identify any betting edges.

---

## 📁 Project Structure

* `nba_engine_ui.py`: The interactive command-line interface.
* `nba_analytics.py`: Core logic for Four-Factor and Fatigue calculations.
* `requirements.txt`: List of required Python packages (`nba_api`, `pandas`, `scikit-learn`).

