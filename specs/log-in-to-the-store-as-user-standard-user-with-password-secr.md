# Test Plan — log in to the store as user standard_user with password secret_sauce

- **Generated**: 2026-07-12 01:04
- **Mode**: pytest
- **Target URL**: https://www.saucedemo.com
- **Browser**: chrome (headless=False)

## Page Objects

- `LoginPage`
- `InventoryPage`

## Scenarios

### TC001 — Login with valid standard_user credentials redirects to Inventory page

Verifies that a valid login with standard_user/secret_sauce navigates to the inventory page.

**Steps:**
1. open LoginPage.URL
1. type Username on LoginPage
1. type Password on LoginPage
1. click Login on LoginPage
1. wait_for_url('/inventory.html')
1. interact with InventoryPage

**Expected:** User is authenticated and redirected to the inventory page; current URL contains '/inventory.html'.

**Test data:** `{"username": "standard_user", "password": "secret_sauce"}`

## Locators (from live DOM scan)

| Page Object | Element | Selector | Wait |
|---|---|---|---|
| LoginPage | Username | `[data-test="username"]` | visible |
| LoginPage | Password | `[data-test="password"]` | visible |
| LoginPage | Login | `[data-test="login-button"]` | clickable |

## Notes

Multi-page flow uses separate page objects (LoginPage → InventoryPage). Only scanned DOM locators used. After clicking Login, wait_for_url('/inventory.html') is required. Use safe_type for inputs on SPA/React forms.
