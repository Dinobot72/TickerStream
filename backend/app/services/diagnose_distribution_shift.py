"""
diagnose_screener.py

Isolates which constraint(s) in the pullback screener are producing 0
results - loosens one filter at a time so we know whether it's a sign/
scale bug on lastclose52weekhigh.lasttwelvemonths or just genuinely
tight market conditions right now.

Run from backend/:
    python diagnose_screener.py
"""
import yfinance as yf
from yfinance import EquityQuery

MIN_PRICE, MAX_PRICE = 10.00, 500.00
MIN_VOLUME = 500_000
MIN_MARKET_CAP = 2_000_000_000
PULLBACK_MIN_PCT, PULLBACK_MAX_PCT = -50.0, -10.0


def count(label, query):
    try:
        r = yf.screen(query, size=5)
        n = len(r.get('quotes', [])) if r else 0
        print(f"{label}: {n} result(s)" + (f" (showing up to 5)" if n else ""))
        for q in (r.get('quotes', []) if r else [])[:5]:
            print(f"    {q.get('symbol')}: price={q.get('regularMarketPrice')} "
                  f"52wHighField={q.get('lastclose52weekhigh.lasttwelvemonths')} "
                  f"marketcap={q.get('marketCap')}")
    except Exception as e:
        print(f"{label}: ERROR - {e}")


base = [EquityQuery('eq', ['region', 'us'])]

print("--- Step 1: just region=us (sanity check the API works at all) ---")
# Just pass the single query directly instead of using 'and'
count("region only", base[0])

print("\n--- Step 2: + price range ---")
# This works fine because base (1 item) + the btwn query (1 item) = 2 operands
count("+ price range", EquityQuery('and', base + [
    EquityQuery('btwn', ['intradayprice', MIN_PRICE, MAX_PRICE]),
]))

print("\n--- Step 3: + volume ---")
count("+ volume", EquityQuery('and', base + [
    EquityQuery('btwn', ['intradayprice', MIN_PRICE, MAX_PRICE]),
    EquityQuery('gt', ['dayvolume', MIN_VOLUME]),
]))

print("\n--- Step 4: + market cap ---")
count("+ market cap", EquityQuery('and', base + [
    EquityQuery('btwn', ['intradayprice', MIN_PRICE, MAX_PRICE]),
    EquityQuery('gt', ['dayvolume', MIN_VOLUME]),
    EquityQuery('gt', ['intradaymarketcap', MIN_MARKET_CAP]),
]))

print("\n--- Step 5: + pullback band (the full query) ---")
count("+ pullback band", EquityQuery('and', base + [
    EquityQuery('btwn', ['intradayprice', MIN_PRICE, MAX_PRICE]),
    EquityQuery('gt', ['dayvolume', MIN_VOLUME]),
    EquityQuery('gt', ['intradaymarketcap', MIN_MARKET_CAP]),
    EquityQuery('btwn', ['lastclose52weekhigh.lasttwelvemonths', PULLBACK_MIN_PCT, PULLBACK_MAX_PCT]),
]))

print("\n--- Step 6: sanity check field sign - any $2B+ stock, sorted by the field ascending ---")
try:
    r = yf.screen(
        EquityQuery('and', base + [EquityQuery('gt', ['intradaymarketcap', MIN_MARKET_CAP])]),
        sortField='lastclose52weekhigh.lasttwelvemonths', sortAsc=True, size=5,
    )
    for q in (r.get('quotes', []) if r else [])[:5]:
        print(f"    {q.get('symbol')}: 52wHighField={q.get('lastclose52weekhigh.lasttwelvemonths')}")
    print("If these numbers are POSITIVE, the field/sign assumption in screener.py is "
          "backwards - flip PULLBACK_MIN_PCT/PULLBACK_MAX_PCT to positive values instead.")
except Exception as e:
    print(f"ERROR - {e}")