# Test Plan — Complete purchase of Sauce Labs Backpack and logout

- **Generated**: 2026-07-12 00:51
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

### TC001 — Login, purchase Sauce Labs Backpack, verify confirmation, and logout

**Steps:**
1. **Given** I am on the Login page at https://www.saucedemo.com
1. **And** I wait until the Username and Password fields are visible
1. **When** I safe_type the username 'standard_user' into the Username field
1. **And** I safe_type the password 'secret_sauce' into the Password field
1. **And** I click the Login button
1. **Then** I wait_for_url to contain 'inventory.html'
1. **When** I add the product 'Sauce Labs Backpack' to the cart on the Inventory page
1. **And** I click the Cart icon to open the cart
1. **Then** I wait_for_url to contain 'cart.html'
1. **And** I should see 'Sauce Labs Backpack' listed in the cart
1. **When** I click the Checkout button
1. **Then** I wait_for_url to contain 'checkout-step-one.html'
1. **When** I safe_type a random First Name into the First Name field
1. **And** I safe_type a random Last Name into the Last Name field
1. **And** I safe_type a random Postal Code into the Postal Code field
1. **And** I click the Continue button
1. **Then** I wait_for_url to contain 'checkout-step-two.html'
1. **And** I should see 'Sauce Labs Backpack' in the Order Summary
1. **When** I click the Finish button
1. **Then** I wait_for_url to contain 'checkout-complete.html'
1. **And** I should see the confirmation message 'Thank you for your order!'
1. **When** I open the burger menu
1. **And** I click Logout
1. **Then** I wait_for_url to equal 'https://www.saucedemo.com/' or contain 'saucedemo.com' without a path
1. **And** I should see the Login button visible on the Login page

**Expected:** User successfully completes checkout of 'Sauce Labs Backpack', sees 'Thank you for your order!' on the checkout complete page, then logs out and is returned to the login page with the login elements visible.

**Test data:** `{"username": "standard_user", "password": "secret_sauce", "product_name": "Sauce Labs Backpack", "first_name": "GENERATE_UNIQUE_AT_RUNTIME", "last_name": "GENERATE_UNIQUE_AT_RUNTIME", "postal_code": "GENERATE_UNIQUE_AT_RUNTIME"}`

## Locators (from live DOM scan)

| Page Object | Element | Selector | Wait |
|---|---|---|---|
| LoginPage | Username input | `[data-test="username"]` | visible |
| LoginPage | Password input | `[data-test="password"]` | visible |
| LoginPage | Login button | `[data-test="login-button"]` | clickable |

## Notes

This test plan follows strict page object separation: one class per page (LoginPage, InventoryPage, CartPage, CheckoutInformationPage, CheckoutOverviewPage, CheckoutCompletePage, MenuPage). Fluent waits are used for inputs (visible), buttons (clickable), and wait_for_url() is applied after each navigation click. Only verified DOM locators provided for the Login page per the supplied scan. Before automation, perform a DOM scan on Inventory, Cart, Checkout (Step One & Two), Complete, and Menu to capture their actual data-test or id attributes (CSS preferred). Typical Saucedemo elements to confirm during scan include: add-to-cart for the backpack, shopping cart link, checkout, firstName, lastName, postalCode, continue, finish, burger menu button, logout link, and the completion header text. Use safe_type for all form inputs. No time.sleep; no hard waits. Each run must generate unique first/last name and postal code to avoid test data collisions.
