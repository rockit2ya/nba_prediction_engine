#!/usr/bin/env python3
"""
NBA Team Advanced Stats Fetcher (Playwright Headless)
- Scrapes NBA.com 'Advanced' tab for OFF_RATING, DEF_RATING, NET_RATING, PACE
- Fully automated, robust headless mode
- Writes to nba_stats_cache.json in model-ready format
"""
import asyncio
import json
import pandas as pd
from datetime import datetime
from playwright.async_api import async_playwright

NBA_ADV_URL = "https://www.nba.com/stats/teams/advanced"
CACHE_FILE = "nba_stats_cache.json"
LOG_FILE = "nba_data_fetcher.log"

# --- Utility Functions ---
def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now()}] {msg}\n")
    print(msg)

def validate_stats(df):
    if df.isnull().any().any():
        return False
    return True

async def fetch_nba_advanced_stats():
    log("Starting NBA.com Advanced tab Playwright headless scrape...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-http2',
                '--disable-features=NetworkService,NetworkServiceInProcess',
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-gpu',
                '--disable-dev-shm-usage',
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )
        page = await context.new_page()
        await page.goto(NBA_ADV_URL)
        # Accept cookie/privacy popup if present
        try:
            await page.click("button:has-text('Accept')", timeout=5000)
            log("Accepted cookie/privacy popup.")
        except Exception:
            pass
        # Scroll to bottom to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(3)
        # Wait for table
        await page.wait_for_selector(".Crom_table__p1iZz", timeout=30000)
        table = await page.query_selector(".Crom_table__p1iZz")
        rows = await table.query_selector_all("tr")
        log(f"Found {len(rows)} rows in the table.")
        # Header
        header_row = await rows[0].query_selector_all("th")
        header_names = [await h.inner_text() for h in header_row]
        header_names = [h.strip().upper() for h in header_names]
        log(f"Header columns: {header_names}")
        def find_col_idx(name):
            for i, col in enumerate(header_names):
                if name in col:
                    return i
            return -1
        idx_team = find_col_idx("TEAM")
        idx_off = find_col_idx("OFFRTG")
        idx_def = find_col_idx("DEFRTG")
        idx_net = find_col_idx("NETRTG")
        idx_pace = find_col_idx("PACE")
        log(f"Indices - TEAM: {idx_team}, OFF: {idx_off}, DEF: {idx_def}, NET: {idx_net}, PACE: {idx_pace}")
        data = []
        for row in rows[1:]:
            cols = await row.query_selector_all("td")
            if min(idx_team, idx_off, idx_def, idx_net, idx_pace) < 0 or len(cols) <= max(idx_team, idx_off, idx_def, idx_net, idx_pace):
                continue
            try:
                team = (await cols[idx_team].inner_text()).strip()
                off_val = (await cols[idx_off].inner_text()).strip()
                def_val = (await cols[idx_def].inner_text()).strip()
                net_val = (await cols[idx_net].inner_text()).strip()
                pace_val = (await cols[idx_pace].inner_text()).strip()
                if not team or not all([off_val, def_val, net_val, pace_val]):
                    continue
                off_rating = float(off_val)
                def_rating = float(def_val)
                net_rating = float(net_val)
                pace = float(pace_val)
                log(f"Parsed: TEAM={team}, OFF={off_rating}, DEF={def_rating}, NET={net_rating}, PACE={pace}")
                data.append({
                    'TEAM_NAME': team,
                    'OFF_RATING': off_rating,
                    'DEF_RATING': def_rating,
                    'NET_RATING': net_rating,
                    'PACE': pace
                })
            except Exception:
                continue
        await browser.close()
        df = pd.DataFrame(data)
        if not validate_stats(df):
            log("Data validation failed. Some values missing.")
            return None
        log(f"Scraped {len(df)} teams from NBA.com Advanced tab")
        return df

def save_stats(df):
    json_dict = {}
    for col in df.columns:
        json_dict[col] = df[col].to_dict()
    with open(CACHE_FILE, 'w') as f:
        json.dump(json_dict, f)
    # Always update timestamp file
    from datetime import datetime
    with open('.stats_timestamp', 'w') as tsf:
        tsf.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log(f"✅ Updated {CACHE_FILE} with {len(df)} teams at {datetime.now()}")

async def main():
    df = await fetch_nba_advanced_stats()
    if df is not None:
        save_stats(df)
        log("NBA.com Advanced data fetch complete.")
        return
    log("All automated fetches failed. Please update manually.")
    print("Manual update required: Copy/paste stats from NBA.com Advanced tab.")

if __name__ == "__main__":
    asyncio.run(main())
