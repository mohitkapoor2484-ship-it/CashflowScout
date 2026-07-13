# Cashflow Scout

Streamlit tool for quickly screening an investment property purchase.

## What it does

- Captures the purchase, rent, rates, insurance, finance, depreciation and tax inputs shown in the source sheet
- Imports editable listing facts from a `realestate.com.au` URL, with a dedicated mobile/desktop pasted-details workflow when REA blocks the link
- Shows key property facts including price guide, type, beds, baths, cars, land size and tenancy status
- Includes an address finder so you can search for and apply a structured Australian property address
- Attempts to look up the Victorian Statement of Information price range from `realestate.com.au`, accepting values only when the source document matches the exact property address
- Supports verified SOI PDF upload when REA blocks automatic access; failed lookups keep existing values for the same property
- Auto-calculates stamp duty from price for supported states
- Estimates annual pre-tax and after-tax cash flow with vacancy and maintenance allowances
- Shows funding required, loan split, leverage and yield
- Provides a five-year value, debt, equity and cash-flow projection using editable growth assumptions
- Scores yield, growth and risk, then gives a transparent `BUY`, `WATCH` or `AVOID` screening recommendation
- Includes a quick rent/rate sensitivity table for investor screening
- Compares the key investment metrics for all locally saved properties
- Shows mortgage principal, annual interest and tenure-interest curves
- Exports the calculated property analysis as a shareable multi-page PDF report
- Saves property scenarios into a local SQLite database and lets you load them from the left sidebar tree

## Run

Install dependencies:

```powershell
pip install -r requirements.txt
```

Start the app:

```powershell
streamlit run app.py
```

## Notes

- `Income tax rate` is a manual input so you can use your own tax advice or tax-table assumptions.
- `Use suggested funding split` sets Mortgage 1 to deposit plus buying costs when the deposit source is `Equity`, and Mortgage 2 to the remaining purchase price.
- SOI auto-fill is intended for Victorian sale listings and depends on the REA listing or linked document being publicly accessible. For a reliable mobile or desktop workflow, download the listing's SOI PDF and upload it in the dashboard; the file is accepted only when its address matches the selected property.
- REA can block automated page access. When that happens, paste the listing description or copied page text into the import panel; all imported values remain editable before calculation.
- For pasted imports, include labelled facts such as `3 beds`, `2 baths` and `1 parking`. The parser also accepts forms such as `Beds: 3`, `3 br`, `2 ba` and `1 carpark`.
- Stamp duty auto-calc currently supports VIC investor/general non-PPR rates, NSW general transfer duty rates, and QLD general transfer duty rates.
- Saved properties are stored in `property_check.db` beside the app.
- This is a screening tool, not financial, tax or legal advice.
