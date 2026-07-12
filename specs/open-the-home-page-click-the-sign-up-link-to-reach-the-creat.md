# Test Plan — open the home page, click the Sign up link to reach the Create Account form, fill it with a random first name, a random last name, a unique random email address generated at runtime, and a random password, click the Create button, verify the account was created successfully, and finally log out

- **Generated**: 2026-07-11 23:03
- **Mode**: pytest
- **Target URL**: https://sauce-demo.myshopify.com
- **Browser**: chrome (headless=False)

## Page Objects

- `HomePage`
- `RegisterPage`
- `AccountPage`

## Scenarios

### TC001 — Create Account and Verify Success

This test verifies that a user can create an account successfully and logout.

**Steps:**
1. open HomePage.URL
1. click 'Sign up' on HomePage
1. wait_for_url('/account/register')
1. safe_type 'first_name' on RegisterPage with random first name
1. safe_type 'last_name' on RegisterPage with random last name
1. safe_type 'email' on RegisterPage with unique random email
1. safe_type 'password' on RegisterPage with random password
1. click 'Create' on RegisterPage
1. wait_for_url('/account')
1. verify account creation success message is visible
1. click 'Log Out' on AccountPage
1. wait_for_url('/account/login')

**Expected:** Account is created successfully and user is redirected to the login page.

**Test data:** `{"first_name": "GENERATE_UNIQUE_AT_RUNTIME", "last_name": "GENERATE_UNIQUE_AT_RUNTIME", "email": "GENERATE_UNIQUE_AT_RUNTIME", "password": "GENERATE_UNIQUE_AT_RUNTIME"}`

## Locators (from live DOM scan)

| Page Object | Element | Selector | Wait |
|---|---|---|---|
| HomePage | Sign up link | `//a[@id='customer_register_link']` | clickable |
| RegisterPage | first_name | `#first_name #first_name` | visible |
| RegisterPage | last_name | `#last_name #last_name` | visible |
| RegisterPage | email | `#email #email` | visible |
| RegisterPage | password | `#password #password` | visible |
| RegisterPage | Create button | `#create_customer input[type='submit']` | clickable |
| AccountPage | Log Out | `//a[@id='customer_logout_link']` | clickable |
