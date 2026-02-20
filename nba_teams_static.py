"""
nba_teams_static.py — Local NBA team data (replaces nba_api.stats.static)

This module provides the same team lookup functions as nba_api.stats.static.teams
but without any external dependency or network calls. The data is hardcoded for
the 30 current NBA teams.

Usage:
    from nba_teams_static import get_teams, TEAM_ID_TO_NAME, TEAM_NAME_TO_ID, NICKNAME_MAP
"""

# ─── Static Team Data ─────────────────────────────────────────────────────────
_NBA_TEAMS = [
    {'id': 1610612737, 'full_name': 'Atlanta Hawks', 'nickname': 'Hawks', 'abbreviation': 'ATL'},
    {'id': 1610612738, 'full_name': 'Boston Celtics', 'nickname': 'Celtics', 'abbreviation': 'BOS'},
    {'id': 1610612739, 'full_name': 'Cleveland Cavaliers', 'nickname': 'Cavaliers', 'abbreviation': 'CLE'},
    {'id': 1610612740, 'full_name': 'New Orleans Pelicans', 'nickname': 'Pelicans', 'abbreviation': 'NOP'},
    {'id': 1610612741, 'full_name': 'Chicago Bulls', 'nickname': 'Bulls', 'abbreviation': 'CHI'},
    {'id': 1610612742, 'full_name': 'Dallas Mavericks', 'nickname': 'Mavericks', 'abbreviation': 'DAL'},
    {'id': 1610612743, 'full_name': 'Denver Nuggets', 'nickname': 'Nuggets', 'abbreviation': 'DEN'},
    {'id': 1610612744, 'full_name': 'Golden State Warriors', 'nickname': 'Warriors', 'abbreviation': 'GSW'},
    {'id': 1610612745, 'full_name': 'Houston Rockets', 'nickname': 'Rockets', 'abbreviation': 'HOU'},
    {'id': 1610612746, 'full_name': 'Los Angeles Clippers', 'nickname': 'Clippers', 'abbreviation': 'LAC'},
    {'id': 1610612747, 'full_name': 'Los Angeles Lakers', 'nickname': 'Lakers', 'abbreviation': 'LAL'},
    {'id': 1610612748, 'full_name': 'Miami Heat', 'nickname': 'Heat', 'abbreviation': 'MIA'},
    {'id': 1610612749, 'full_name': 'Milwaukee Bucks', 'nickname': 'Bucks', 'abbreviation': 'MIL'},
    {'id': 1610612750, 'full_name': 'Minnesota Timberwolves', 'nickname': 'Timberwolves', 'abbreviation': 'MIN'},
    {'id': 1610612751, 'full_name': 'Brooklyn Nets', 'nickname': 'Nets', 'abbreviation': 'BKN'},
    {'id': 1610612752, 'full_name': 'New York Knicks', 'nickname': 'Knicks', 'abbreviation': 'NYK'},
    {'id': 1610612753, 'full_name': 'Orlando Magic', 'nickname': 'Magic', 'abbreviation': 'ORL'},
    {'id': 1610612754, 'full_name': 'Indiana Pacers', 'nickname': 'Pacers', 'abbreviation': 'IND'},
    {'id': 1610612755, 'full_name': 'Philadelphia 76ers', 'nickname': '76ers', 'abbreviation': 'PHI'},
    {'id': 1610612756, 'full_name': 'Phoenix Suns', 'nickname': 'Suns', 'abbreviation': 'PHX'},
    {'id': 1610612757, 'full_name': 'Portland Trail Blazers', 'nickname': 'Trail Blazers', 'abbreviation': 'POR'},
    {'id': 1610612758, 'full_name': 'Sacramento Kings', 'nickname': 'Kings', 'abbreviation': 'SAC'},
    {'id': 1610612759, 'full_name': 'San Antonio Spurs', 'nickname': 'Spurs', 'abbreviation': 'SAS'},
    {'id': 1610612760, 'full_name': 'Oklahoma City Thunder', 'nickname': 'Thunder', 'abbreviation': 'OKC'},
    {'id': 1610612761, 'full_name': 'Toronto Raptors', 'nickname': 'Raptors', 'abbreviation': 'TOR'},
    {'id': 1610612762, 'full_name': 'Utah Jazz', 'nickname': 'Jazz', 'abbreviation': 'UTA'},
    {'id': 1610612763, 'full_name': 'Memphis Grizzlies', 'nickname': 'Grizzlies', 'abbreviation': 'MEM'},
    {'id': 1610612764, 'full_name': 'Washington Wizards', 'nickname': 'Wizards', 'abbreviation': 'WAS'},
    {'id': 1610612765, 'full_name': 'Detroit Pistons', 'nickname': 'Pistons', 'abbreviation': 'DET'},
    {'id': 1610612766, 'full_name': 'Charlotte Hornets', 'nickname': 'Hornets', 'abbreviation': 'CHA'},
]


def get_teams():
    """Return list of all NBA teams (same signature as nba_api.stats.static.teams.get_teams)."""
    return list(_NBA_TEAMS)


# ─── Prebuilt Lookup Dicts ────────────────────────────────────────────────────
TEAM_ID_TO_NAME = {t['id']: t['full_name'] for t in _NBA_TEAMS}
TEAM_NAME_TO_ID = {t['full_name']: t['id'] for t in _NBA_TEAMS}
NICKNAME_MAP = {t['nickname']: t for t in _NBA_TEAMS}
ABBREV_MAP = {t['abbreviation']: t for t in _NBA_TEAMS}

# Common aliases
NICKNAME_ALIASES = {
    'Blazers': 'Trail Blazers',
    'Sixers': '76ers',
    'Wolves': 'Timberwolves',
}


def find_team_by_name(name):
    """Fuzzy team finder: accepts full name, nickname, abbreviation, or alias."""
    name = name.strip()
    # Full name
    for t in _NBA_TEAMS:
        if t['full_name'].lower() == name.lower():
            return t
    # Nickname
    for t in _NBA_TEAMS:
        if t['nickname'].lower() == name.lower():
            return t
    # Abbreviation
    for t in _NBA_TEAMS:
        if t['abbreviation'].lower() == name.lower():
            return t
    # Alias
    if name in NICKNAME_ALIASES:
        canonical = NICKNAME_ALIASES[name]
        return NICKNAME_MAP.get(canonical)
    return None
