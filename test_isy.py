import isyatirimhisse as isy
try:
    df = isy.fetch_financials(["BIMAS"], exchange="TRY")
    print(df.head())
except Exception as e:
    print(e)
