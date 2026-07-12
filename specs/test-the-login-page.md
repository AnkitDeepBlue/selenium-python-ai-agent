# Test Plan — test the login page

- **Generated**: 2026-07-11 15:45
- **Mode**: pytest
- **Target URL**: https://www.saucedemo.com
- **Browser**: chrome (headless=False)

## Page Objects

- `LoginPage`

## Scenarios

### TC001 — Successful Login

Verify that a user can successfully log in with valid credentials.

**Steps:**
1. open LoginPage.URL
1. type USERNAME_INPUT on LoginPage
1. type PASSWORD_INPUT on LoginPage
1. click LOGIN_BUTTON on LoginPage
1. wait_for_url('/inventory.html')

**Expected:** User is redirected to the inventory page.

**Test data:** `{"username": "standard_user", "password": "secret_sauce"}`

### TC002 — Unsuccessful Login with Invalid Credentials

Verify that a user cannot log in with invalid credentials.

**Steps:**
1. open LoginPage.URL
1. type USERNAME_INPUT on LoginPage
1. type INVALID_PASSWORD_INPUT on LoginPage
1. click LOGIN_BUTTON on LoginPage
1. wait_for_url('/')

**Expected:** Error message is displayed and user remains on the login page.

**Test data:** `{"username": "standard_user", "password": "wrong_password"}`

## Locators (from live DOM scan)

| Page Object | Element | Selector | Wait |
|---|---|---|---|
| LoginPage | Username input field | `input[data-test='username']` | visible |
| LoginPage | Password input field | `input[data-test='password']` | visible |
| LoginPage | Login button | `input[data-test='login-button']` | clickable |
| LoginPage | Error message | `h3[data-test='error']` | visible |
