# Test Plan — User can purchase a product and logout

- **Generated**: 2026-07-12 00:34
- **Mode**: bdd
- **Target URL**: https://www.saucedemo.com
- **Browser**: chrome (headless=False)

## Page Objects

- `LoginPage`
- `InventoryPage`
- `CartPage`
- `CheckoutInformationPage`
- `CheckoutOverviewPage`
- `CheckoutCompletePage`
- `MenuPage`

## Scenarios

### TC001 — Happy path: Login, add Sauce Labs Backpack, checkout to completion, and logout

**Steps:**
1. **Given** I am on the Login page at https://www.saucedemo.com
1. **When** I safe_type(LoginPage, LoginPage.USERNAME_INPUT, "standard_user")
1. **And** I safe_type(LoginPage, LoginPage.PASSWORD_INPUT, "secret_sauce")
1. **And** I click the LoginPage.LOGIN_BUTTON
1. **Then** I wait_for_url("/inventory.html")
1. **When** On the Inventory page, I click the Add to cart button for product "Sauce Labs Backpack"
1. **And** I click the cart icon to open the Cart page
1. **Then** I wait_for_url("/cart.html")
1. **And** I should see the product line item "Sauce Labs Backpack" listed in the cart
1. **When** I click the Checkout button
1. **Then** I wait_for_url("/checkout-step-one.html")
1. **When** I safe_type(CheckoutInformationPage, CheckoutInformationPage.FIRST_NAME_INPUT, <first_name>)
1. **And** I safe_type(CheckoutInformationPage, CheckoutInformationPage.LAST_NAME_INPUT, <last_name>)
1. **And** I safe_type(CheckoutInformationPage, CheckoutInformationPage.POSTAL_CODE_INPUT, <postal_code>)
1. **And** I click the Continue button
1. **Then** I wait_for_url("/checkout-step-two.html")
1. **And** I should see the order summary contains product "Sauce Labs Backpack"
1. **When** I click the Finish button
1. **Then** I wait_for_url("/checkout-complete.html")
1. **And** I should see the confirmation message "Thank you for your order!"
1. **When** I open the burger menu
1. **And** I click Logout
1. **Then** I wait_for_url("/")
1. **And** I should see the Login page username, password fields and login button visible

**Expected:** User is logged in, product 'Sauce Labs Backpack' is purchased successfully with confirmation message displayed, and user is logged out and returned to the login page.

**Test data:** `{"username": "standard_user", "password": "secret_sauce", "product_name": "Sauce Labs Backpack", "first_name": "GENERATE_UNIQUE_AT_RUNTIME", "last_name": "GENERATE_UNIQUE_AT_RUNTIME", "postal_code": "GENERATE_UNIQUE_AT_RUNTIME"}`

## Locators (from live DOM scan)

| Page Object | Element | Selector | Wait |
|---|---|---|---|
| LoginPage | USERNAME_INPUT | `[data-test="username"]` | visible |
| LoginPage | PASSWORD_INPUT | `[data-test="password"]` | visible |
| LoginPage | LOGIN_BUTTON | `[data-test="login-button"]` | clickable |

## Notes

Important: This plan enforces separate page objects for each page in the flow. Use fluent_wait for elements (visible for inputs, clickable for buttons/links), and call wait_for_url() after each navigation action as shown in steps. Only the Login page DOM locators were provided by the scan; before implementation, perform a DOM scan on Inventory, Cart, Checkout Step One, Checkout Step Two, Checkout Complete, and the Menu to capture their data-test or id-based selectors. Do not invent locators. For form fields on CheckoutInformationPage, use safe_type() to ensure React inputs are populated reliably. No time.sleep() should be used; rely on fluent waits and loader invisibility if loaders exist. Each test run must generate unique first name, last name, and postal code values at runtime to avoid collisions in test data storage and logs.
