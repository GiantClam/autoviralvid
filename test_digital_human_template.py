from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # Non-headless to see what's happening
    page = browser.new_page()
    
    # Navigate to localhost:3000
    print("Navigating to http://localhost:3000...")
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    
    # Take first screenshot
    print("Taking initial screenshot...")
    page.screenshot(path='screenshot_1_initial.png', full_page=True)
    print("Screenshot saved to screenshot_1_initial.png")
    
    # Wait a bit for any animations
    time.sleep(1)
    
    # Look for the Digital Human template card - scroll down to find it
    print("\nSearching for Digital Human (数字人口播) template card...")
    
    # First, let's see all text on the page
    all_text = page.locator('body').inner_text()
    print(f"\nPage contains '数字人口播': {'数字人口播' in all_text}")
    print(f"Page contains '数字人': {'数字人' in all_text}")
    
    # Scroll down to reveal more templates
    page.evaluate('window.scrollBy(0, 500)')
    time.sleep(1)
    
    # Take screenshot after scrolling
    page.screenshot(path='screenshot_1b_after_scroll.png', full_page=True)
    print("Screenshot after scroll saved to screenshot_1b_after_scroll.png")
    
    # Try to find by text content - more specific search
    digital_human_selectors = [
        'text="数字人口播"',
        'text=/数字人口播/',
        'text=/.*数字人口播.*/',
        'div:has-text("数字人口播")',
        'button:has-text("数字人口播")',
        '[class*="card"]:has-text("数字人口播")',
        'a:has-text("数字人口播")',
    ]
    
    found = False
    clicked_element = None
    
    for selector in digital_human_selectors:
        try:
            elements = page.locator(selector).all()
            if len(elements) > 0:
                for elem in elements:
                    if elem.is_visible(timeout=1000):
                        print(f"Found element with selector: {selector}")
                        clicked_element = elem
                        found = True
                        break
                if found:
                    break
        except Exception as e:
            continue
    
    if not found:
        # Let's inspect all clickable elements more carefully
        print("\nSearching through all clickable elements...")
        
        # Get all potential template cards
        cards = page.locator('[class*="card"], [class*="template"], div[role="button"], button, a').all()
        print(f"Found {len(cards)} potential cards/buttons")
        
        for i, card in enumerate(cards):
            try:
                text = card.inner_text()
                if '数字人' in text:
                    print(f"Card {i}: {text[:200]}")
                    if '口播' in text or '数字人口播' in text:
                        print(f"  -> This looks like the Digital Human card!")
                        clicked_element = card
                        found = True
                        break
            except:
                continue
    
    if found:
        print(f"\nClicking on Digital Human template card...")
        clicked_element.click()
        
        # Wait for navigation or content change
        time.sleep(2)
        page.wait_for_load_state('networkidle')
        
        # Take second screenshot after clicking
        print("Taking screenshot after click...")
        page.screenshot(path='screenshot_2_after_click.png', full_page=True)
        print("Screenshot saved to screenshot_2_after_click.png")
    else:
        print("\n❌ Could not find Digital Human (数字人口播) template card on the page")
        print("Please check the screenshots to see what's available")
        
        # Let's print all text containing '数字' to help debug
        print("\nAll elements containing '数字':")
        all_elements = page.locator('*').all()
        for elem in all_elements[:100]:
            try:
                text = elem.inner_text()
                if '数字' in text and len(text) < 100:
                    print(f"  - {text}")
            except:
                continue
    
    # Keep browser open for a moment
    time.sleep(2)
    browser.close()
    print("\nDone!")
