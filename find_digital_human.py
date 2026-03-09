from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Navigate to localhost:3000
    print("Navigating to http://localhost:3000...")
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    time.sleep(2)
    
    # Get all text on page
    print("\n=== Searching for all elements with '数字人' ===")
    
    # Method 1: Search all elements
    all_elements = page.locator('*').all()
    digital_human_elements = []
    
    for i, elem in enumerate(all_elements):
        try:
            text = elem.inner_text(timeout=100)
            if '数字人' in text and len(text) < 200:
                print(f"\nElement {i}:")
                print(f"  Text: {text}")
                print(f"  Tag: {elem.evaluate('el => el.tagName')}")
                print(f"  Classes: {elem.get_attribute('class')}")
                print(f"  Visible: {elem.is_visible()}")
                digital_human_elements.append((i, elem, text))
        except:
            continue
    
    print(f"\n\n=== Found {len(digital_human_elements)} elements with '数字人' ===")
    
    # Take a full page screenshot
    page.screenshot(path='full_page.png', full_page=True)
    print("\nFull page screenshot saved to full_page.png")
    
    # Try to find cards specifically
    print("\n=== Looking for template cards ===")
    card_selectors = [
        '[class*="card"]',
        '[class*="template"]',
        '[class*="Card"]',
        '[class*="Template"]',
        'div[role="button"]',
        'button',
        'a[href]'
    ]
    
    for selector in card_selectors:
        try:
            cards = page.locator(selector).all()
            print(f"\nSelector '{selector}': found {len(cards)} elements")
            for i, card in enumerate(cards[:10]):  # Check first 10
                try:
                    text = card.inner_text(timeout=100)
                    if '数字人' in text or '口播' in text:
                        print(f"  Card {i}: {text[:100]}")
                except:
                    pass
        except:
            continue
    
    # Keep browser open
    time.sleep(3)
    browser.close()
    print("\nDone!")
