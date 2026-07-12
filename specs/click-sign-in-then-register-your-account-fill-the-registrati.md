# Test Plan — click Sign in then Register your account, fill the registration form with random data and a unique random email generated at runtime, submit it, and verify the account was created

- **Generated**: 2026-07-11 23:43
- **Mode**: pytest
- **Target URL**: https://practicesoftwaretesting.com
- **Browser**: chrome (headless=False)

## Page Objects

- `HomePage`
- `LoginPage`
- `RegisterPage`

## Scenarios

### TC001 — Register new account

Registers a new account with random data and verifies account creation.

**Steps:**
1. open LoginPage.URL
1. click [Sign in] on HomePage
1. click [Register your account] on LoginPage
1. wait_for_url('auth/register')
1. type [First name *] on RegisterPage
1. type [Your last name *] on RegisterPage
1. type [YYYY-MM-DD] on RegisterPage
1. select [Your country *] on RegisterPage
1. type [Your Postcode *] on RegisterPage
1. type [e.g. 42 *] on RegisterPage
1. type [Your Street *] on RegisterPage
1. type [Your City *] on RegisterPage
1. type [Your State *] on RegisterPage
1. type [Your phone *] on RegisterPage
1. type [Your email *] on RegisterPage
1. type [Your password] on RegisterPage
1. click [Register] on RegisterPage
1. wait_for_url('welcome')

**Expected:** User should see a welcome message confirming account creation.

**Test data:** `{"first_name": "John", "last_name": "Doe", "dob": "1990-01-01", "country": "Albania", "postcode": "12345", "house_number": "42", "street": "Main Street", "city": "Tirana", "state": "Tirana", "phone": "+355692345678", "email": "GENERATE_UNIQUE_AT_RUNTIME", "password": "Str0ngPa$$w0rd"}`

## Locators (from live DOM scan)

| Page Object | Element | Selector | Wait |
|---|---|---|---|
| HomePage | Sign in | `[data-test="nav-sign-in"]` | clickable |
| LoginPage | Register your account | `[data-test="register-link"]` | clickable |
| RegisterPage | First name | `[data-test="first-name"]` | visible |
| RegisterPage | Last name | `[data-test="last-name"]` | visible |
| RegisterPage | Date of Birth | `[data-test="dob"]` | visible |
| RegisterPage | Country | `[data-test="country"]` | visible |
| RegisterPage | Postal code | `[data-test="postal_code"]` | visible |
| RegisterPage | House number | `[data-test="house_number"]` | visible |
| RegisterPage | Street | `[data-test="street"]` | visible |
| RegisterPage | City | `[data-test="city"]` | visible |
| RegisterPage | State | `[data-test="state"]` | visible |
| RegisterPage | Phone | `[data-test="phone"]` | visible |
| RegisterPage | Email | `[data-test="email"]` | visible |
| RegisterPage | Password | `[data-test="password"]` | visible |
| RegisterPage | Register Button | `[data-test="register-submit"]` | clickable |

## Notes

Ensure unique email generation at runtime to prevent collision.
