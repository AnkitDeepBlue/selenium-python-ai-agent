# Test Plan — search for 'macbook' and verify results show prices

- **Generated**: 2026-07-11 16:41
- **Mode**: pytest
- **Target URL**: https://demo.opencart.com
- **Browser**: chrome (headless=False)

## Page Objects

- `SearchPage`
- `SearchResultsPage`

## Scenarios

### TC001 — Search for MacBook and verify results show prices

This test verifies that searching for 'macbook' displays product prices on the results page.

**Steps:**
1. open https://demo.opencart.com
1. type 'macbook' on SearchPage
1. click SearchButton on SearchPage
1. wait_for_url('search=macbook')
1. verify prices are visible on SearchResultsPage

**Expected:** The search results display prices for the MacBook products.

**Test data:** `{"search_term": "macbook"}`

## Locators (from live DOM scan)

| Page Object | Element | Selector | Wait |
|---|---|---|---|
| SearchPage | Search input field | `input[name='search']` | visible |
| SearchPage | Search button | `button[type='button'][class='btn btn-default btn-lg']` | clickable |
| SearchResultsPage | Product prices | `.price` | visible |
