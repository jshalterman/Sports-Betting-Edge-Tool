from thefuzz import fuzz

def is_player_match(odds_api_name: str, kalshi_player_name: str, threshold: int = 85) -> bool:
    """
    Compares two player names using fuzzy ratio matching.
    Returns True if similarity score is above the threshold.
    """
    # Normalize strings (lowercase, strip whitespace)
    name1 = odds_api_name.lower().strip().replace(".", "")
    name2 = kalshi_player_name.lower().strip().replace(".", "")
    
    # Check partial and token sort ratios
    ratio = fuzz.token_sort_ratio(name1, name2)
    return ratio >= threshold

def parse_kalshi_strikeout_market(ticker: str, title: str) -> dict:
    """
    Parses a Kalshi market title/ticker into player name, strikeout line, and side.
    Example Title: 'Will Tarik Skubal record over 6.5 strikeouts?'
    """
    # Simple extraction logic tailored to Kalshi naming conventions
    title_clean = title.replace("Will ", "").replace(" record over", "").replace(" strikeouts?", "").strip()
    
    parts = title_clean.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].replace(".", "").isdigit():
        player_name = parts[0]
        strikeout_line = float(parts[1])
        return {
            "player_name": player_name,
            "line": strikeout_line,
            "ticker": ticker
        }
    return None

# Quick Check
if __name__ == "__main__":
    player_a = "A.J. Puk"
    player_b = "AJ Puk"
    
    match_result = is_player_match(player_a, player_b)
    print(f"Matching '{player_a}' with '{player_b}': Match={match_result}")