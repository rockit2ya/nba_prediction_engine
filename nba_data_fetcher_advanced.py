#!/usr/bin/env python3
"""
NBA Team Advanced Stats Fetcher (Headless Browser)
- Scrapes NBA.com 'Advanced' tab for OFF_RATING, DEF_RATING, NET_RATING, PACE
- Fully automated, logs every run, validates data freshness
- Writes to nba_stats_cache.json in model-ready format
"""
import time
import json
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

NBA_ADV_URL = "https://www.nba.com/stats/teams/advanced"
CACHE_FILE = "nba_stats_cache.json"
LOG_FILE = "nba_data_fetcher.log"

# --- Utility Functions ---
def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now()}] {msg}\n")
    print(msg)

def validate_stats(df):
    # Check for missing (NaN) values only
    if df.isnull().any().any():
        return False
    return True

# --- Main Scraper ---
def fetch_nba_advanced_stats():
    log("Starting NBA.com Advanced tab headless scrape...")
    options = Options()
    # options.add_argument('--headless')  # Headless mode disabled for reliability
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    driver.get(NBA_ADV_URL)
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    data = []
    try:
        # Extra wait to ensure page loads fully
        time.sleep(2)
        # Scroll to bottom to trigger lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)  # Wait for JS to load table after scroll
        # Handle cookie/privacy popup if present
        try:
            WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]"))
            ).click()
            log("Accepted cookie/privacy popup.")
            time.sleep(1)
        except Exception:
            log("No cookie/privacy popup found.")
            pass  # No popup

        # Wait up to 30s for the stats table to appear
        table = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "Crom_table__p1iZz"))
        )
        rows = table.find_elements(By.TAG_NAME, "tr")
        log(f"Found {len(rows)} rows in the table.")
        # Print header row for debugging
        header_row = rows[0].find_elements(By.TAG_NAME, "th")
        header_names = [h.text.strip().upper() for h in header_row]
        log(f"Header columns: {header_names}")

        # Map stat names to their indices
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

        for row in rows[1:]:
            cols = row.find_elements(By.TAG_NAME, "td")
            if min(idx_team, idx_off, idx_def, idx_net, idx_pace) < 0 or len(cols) <= max(idx_team, idx_off, idx_def, idx_net, idx_pace):
                log(f"Skipping row due to bad indices or insufficient columns: {[c.text for c in cols]}")
                continue
            try:
                team = cols[idx_team].text.strip()
                off_val = cols[idx_off].text.strip()
                def_val = cols[idx_def].text.strip()
                net_val = cols[idx_net].text.strip()
                pace_val = cols[idx_pace].text.strip()
                # Skip if any value is missing or not a float
                if not team or not all([off_val, def_val, net_val, pace_val]):
                    log(f"Skipping row with missing values: TEAM={team}, OFF={off_val}, DEF={def_val}, NET={net_val}, PACE={pace_val}")
                    continue
                try:
                    off_rating = float(off_val)
                    def_rating = float(def_val)
                    net_rating = float(net_val)
                    pace = float(pace_val)
                except Exception as conv_e:
                    log(f"Skipping row with non-numeric stat: TEAM={team}, OFF={off_val}, DEF={def_val}, NET={net_val}, PACE={pace_val} | Error: {conv_e}")
                    continue
                log(f"Parsed: TEAM={team}, OFF={off_rating}, DEF={def_rating}, NET={net_rating}, PACE={pace}")
                data.append({
                    'TEAM_NAME': team,
                    'OFF_RATING': off_rating,
                    'DEF_RATING': def_rating,
                    'NET_RATING': net_rating,
                    'PACE': pace
                })
            except Exception as parse_e:
                log(f"Failed to parse row: {[c.text for c in cols]} | Error: {parse_e}")
        try:
            driver.quit()
        except Exception as quit_e:
            log(f"driver.quit() failed or window already closed: {quit_e}")
        df = pd.DataFrame(data)
        if not validate_stats(df):
            log("Data validation failed. Some values missing or zero.")
            return None
        log(f"Scraped {len(df)} teams from NBA.com Advanced tab")
        return df
    except Exception as e:
        try:
            driver.quit()
        except Exception as quit_e:
            log(f"driver.quit() failed or window already closed (exception path): {quit_e}")
        log(f"NBA.com Advanced scrape failed: {e}")
        print("\n[ERROR] NBA.com Advanced scrape failed.\nReason:", e)
        print("\nTroubleshooting tips:")
        print("- Make sure the table class name is still 'Crom_table' (inspect NBA.com)")
        print("- Try running with Chrome (not headless) to debug popups or layout changes")
        print("- Check your network connection and try again")
        return None

def save_stats(df):
    # Convert to model format
    json_dict = {}
    for col in df.columns:
        json_dict[col] = df[col].to_dict()
    with open(CACHE_FILE, 'w') as f:
        json.dump(json_dict, f)
    # Always update timestamp file
    with open('.stats_timestamp', 'w') as tsf:
        tsf.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log(f"✅ Updated {CACHE_FILE} with {len(df)} teams at {datetime.now()}")

def main():
    df = fetch_nba_advanced_stats()
    if df is not None:
        save_stats(df)
        log("NBA.com Advanced data fetch complete.")
        return
    log("All automated fetches failed. Please update manually.")
    print("Manual update required: Copy/paste stats from NBA.com Advanced tab.")

if __name__ == "__main__":
    main()
