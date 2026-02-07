import yfinance as yf
from yfinance import EquityQuery
from app.core.database import get_db_connection

# --- CONFIGURATION ---
BOT_USER_ID = 11
MAX_PRICE = 100.00   # Affordability Limit
MIN_PRICE = 2.00    # Penny Stock Filter
MIN_VOLUME = 500_000 # Minimum Liquidity

def run_market_scan():
    print("--- 📡 SENTINEL: Running Advanced yfinance Screen ---")

    # 1. Construct the "Affordable Mover" Query
    # We combine multiple filters using 'and' logic.
    # This asks Yahoo: "Give me US stocks, between $2-$50, with high volume, that are up > 3% today."
    mobile_query = EquityQuery('and', [
        EquityQuery('eq', ['region', 'us']),
        EquityQuery('btwn', ['intradayprice', MIN_PRICE, MAX_PRICE]), # The Price Limit
        EquityQuery('gt', ['dayvolume', MIN_VOLUME]),                 # The Liquidity Check
        EquityQuery('gt', ['percentchange', 3])                       # The Momentum Check
    ])

    try:
        # 2. Execute the Screen
        # sortField='percentchange' ensures we get the biggest winners first.
        # size=25 limits us to the top 25 results.
        response = yf.screen(mobile_query, sortField='percentchange', sortAsc=False, size=25)

        if not response or 'quotes' not in response:
            print("Sentinel: No results returned from Yahoo Screen.")
            return []

        candidates = []
        
        # 3. Parse Results
        # The response['quotes'] contains the metadata we need directly.
        for quote in response['quotes']:
            ticker = quote.get('symbol')
            
            # Skip non-equity results if any sneak in
            if not ticker or quote.get('quoteType') != 'EQUITY':
                continue

            # Extract Clean Data
            price = quote.get('regularMarketPrice') or quote.get('intradayprice')
            change_pct = quote.get('regularMarketChangePercent') or quote.get('percentchange')
            volume = quote.get('regularMarketVolume') or quote.get('dayvolume')

            candidates.append({
                "ticker": ticker,
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            })

        print(f"--- 📡 SENTINEL: Found {len(candidates)} affordable candidates. ---")
        for c in candidates:
            print(f" > {c['ticker']} | Price: ${c['price']} | Change: +{c['change_pct']}%")

        # 4. Save to Database
        update_bot_watchlist(candidates)
        
        # Return list of tickers for immediate use
        return [c['ticker'] for c in candidates]

    except Exception as e:
        print(f"Sentinel Error: Screening failed - {e}")
        return []

def update_bot_watchlist(candidates):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # We append new finds to the watchlist.
    # (Optional: You could delete old ones first if you want a fresh start daily)
    
    count = 0
    for item in candidates:
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO bot_watchlist (user_id, ticker) VALUES (?, ?)",
                (BOT_USER_ID, item['ticker'])
            )
            count += 1
        except Exception:
            pass
            
    conn.commit()
    conn.close()
    print(f"Sentinel: Added {count} new tickers to Bot Watchlist.")

if __name__ == "__main__":
    run_market_scan()