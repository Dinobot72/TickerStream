import yfinance as yf
from yfinance import EquityQuery
from app.core.database import get_db_connection
from app.core.bot_state import get_active_bot_user_ids

# --- CONFIGURATION ---
MAX_PRICE = 500.00       # was 100 - too tight combined with the market-cap floor below
MIN_PRICE = 10.00        # was 2 - $2-10 names are almost always micro/nano-cap, nothing
                          # like the model's S&P-500 training universe
MIN_VOLUME = 500_000     # Minimum Liquidity
MIN_MARKET_CAP = 2_000_000_000  # $2B+ keeps candidates closer to the large/mid-cap
                                 # names the model actually trained on

# Daily move ceiling. We're NOT requiring an active decline (that risks
# "catching a falling knife" - a stock down big today is often down for a
# real reason). We're just excluding stocks that are actively spiking -
# the euphoric-high names this screener used to hunt for on purpose.
# Anything flat-to-moderately-down is fair game; the model's own RSI/SMA
# features (from shared_obs.py) do the real entry-quality judgment once a
# candidate reaches it - the screener's job is just liquidity + not
# chasing today's pump.
MAX_DAILY_MOVE_PCT = 3.0

def run_market_scan():
    print("--- 📡 SENTINEL: Running Advanced yfinance Screen ---")

    # "Not buying the top" screen: US, liquid, large/mid-cap, and NOT up big
    # today. The old query (percentchange > 3, sorted by biggest gainer) was
    # explicitly hunting stocks at a local peak - the opposite of buy-low-
    # sell-high, and it pulled in penny/microcap momentum spikes the model
    # never saw anything like in training.
    #
    # NOTE: an earlier version of this filtered on
    # 'lastclose52weekhigh.lasttwelvemonths' (distance from 52-week high) to
    # get a true pullback signal. Diagnostics showed that field returns None
    # for every quote and silently zeroes out any range filter that uses it -
    # despite being listed as a valid field, it doesn't appear to actually
    # work for this. Dropped it in favor of `percentchange`, which we've
    # directly confirmed returns real data and real filtered results.
    mobile_query = EquityQuery('and', [
        EquityQuery('eq', ['region', 'us']),
        EquityQuery('btwn', ['intradayprice', MIN_PRICE, MAX_PRICE]),
        EquityQuery('gt', ['dayvolume', MIN_VOLUME]),
        EquityQuery('gt', ['intradaymarketcap', MIN_MARKET_CAP]),
        EquityQuery('lt', ['percentchange', MAX_DAILY_MOVE_PCT]),
    ])

    try:
        # 2. Execute the Screen
        # Sort ascending by percentchange so the most-down-today names surface
        # first - closest we can get to "on sale" with a confirmed-working field.
        # size=25 limits to the top 25 results.
        response = yf.screen(mobile_query, sortField='percentchange', sortAsc=True, size=25)

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
            print(f" > {c['ticker']} | Price: ${c['price']} | Change: {c['change_pct']}%")

        # 4. Save to Database
        update_bot_watchlist(candidates)
        
        # Return list of tickers for immediate use
        return [c['ticker'] for c in candidates]

    except Exception as e:
        print(f"Sentinel Error: Screening failed - {e}")
        return []

def update_bot_watchlist(candidates):
    active_user_ids = get_active_bot_user_ids()

    if not active_user_ids:
        print("Sentinel: No users have the bot active — skipping watchlist writes.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    tickers = [c['ticker'] for c in candidates]
    total_inserted = 0

    for user_id in active_user_ids:
        # Remove any previously-added screener tickers for this user that
        # aren't in the current scan results (keeps their bot_watchlist
        # fresh instead of accumulating stale picks forever).
        if tickers:
            cursor.execute(
                "DELETE FROM bot_watchlist WHERE user_id = ? AND ticker NOT IN ({})".format(
                    ",".join("?" * len(tickers))
                ),
                [user_id] + tickers
            )

        for item in candidates:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO bot_watchlist (user_id, ticker) VALUES (?, ?)",
                    # Needs fixed
                    (user_id, item['ticker'])
                )
                total_inserted += 1
            except Exception:
                pass
            
    conn.commit()
    conn.close()
    print(f"Sentinel: Synced {len(candidates)} tickers across {len(active_user_ids)} active bot user(s).")

if __name__ == "__main__":
    run_market_scan()