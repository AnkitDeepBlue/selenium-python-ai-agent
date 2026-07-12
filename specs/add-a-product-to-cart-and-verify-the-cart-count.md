# Test Plan — add a product to cart and verify the cart count

- **Generated**: 2026-07-11 16:42
- **Mode**: pytest
- **Target URL**: https://demo.opencart.com
- **Browser**: chrome (headless=False)

## Page Objects

- `ProductPage`
- `CartPage`

## Scenarios

### TC001 — Add Product to Cart and Verify Cart Count

This test verifies that a product can be added to the cart and the cart count is updated accordingly.

**Steps:**
1. open https://demo.opencart.com
1. click the product link on the main page
1. click 'Add to Cart' button on ProductPage
1. wait_for_url('cart')
1. verify cart count is '1'

**Expected:** The product is added to the cart and the cart count is updated to '1'.

## Locators (from live DOM scan)

| Page Object | Element | Selector | Wait |
|---|---|---|---|
| ProductPage | Add to Cart button | `.btn-add-to-cart` | clickable |
| CartPage | Cart Count | `.cart-count` | visible |
