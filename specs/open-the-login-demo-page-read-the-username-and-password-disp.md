# Test Plan — open the login demo page, read the username and password displayed in the AUTHORIZED CREDENTIALS section on the page, type them into the username and password fields of the AUTHENTICATION INTERFACE form, click the INITIATE LOGIN SEQUENCE button, and verify the login is successful

- **Generated**: 2026-07-11 16:25
- **Mode**: pytest
- **Target URL**: https://testtrack.org/login-demo
- **Browser**: chrome (headless=False)

## Page Objects

- `LoginPage`

## Scenarios

### TC001 — Successful login with authorized credentials

Tests logging in using the credentials provided in the AUTHORIZED CREDENTIALS section.

**Steps:**
1. open LoginPage.URL
1. read the username and password from AUTHORIZED CREDENTIALS section
1. type username into Enter your username on LoginPage
1. type password into Enter your password on LoginPage
1. click INITIATE LOGIN SEQUENCE on LoginPage
1. wait_for_url('/dashboard')

**Expected:** User is successfully logged in and redirected to the dashboard page.

**Test data:** `{"username": "testuser", "password": "password123"}`

## Locators (from live DOM scan)

| Page Object | Element | Selector | Wait |
|---|---|---|---|
| LoginPage | username field | `#username` | visible |
| LoginPage | password field | `#password` | visible |
| LoginPage | initiate login button | `#login-submit` | clickable |
| LoginPage | authorized username display | `//p[contains(normalize-space(), 'USERNAME:')]` | visible |
| LoginPage | authorized password display | `//p[contains(normalize-space(), 'PASSWORD:')]` | visible |
