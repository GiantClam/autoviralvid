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
    
    # Take initial screenshot
    print("\nTaking initial screenshot...")
    page.screenshot(path='screenshot_1_initial.png', full_page=True)
    print("Screenshot saved to screenshot_1_initial.png")
    
    # Find the Digital Human button by its text
    print("\nLooking for Digital Human (数字人口播) button...")
    
    # Use a more specific selector for the button with this exact text
    digital_human_button = page.locator('button:has-text("数字人口播")')
    
    if digital_human_button.count() > 0:
        print(f"Found {digital_human_button.count()} button(s) with '数字人口播'")
        
        # Get the button text to confirm
        button_text = digital_human_button.first.inner_text()
        print(f"Button text: {button_text[:100]}")
        
        # Click the button
        print("\nClicking on Digital Human button...")
        digital_human_button.first.click()
        
        # Wait for the page to load/transition
        time.sleep(2)
        page.wait_for_load_state('networkidle')
        time.sleep(1)
        
        # Take screenshot after clicking
        print("\nTaking screenshot after click...")
        page.screenshot(path='screenshot_2_after_click.png', full_page=True)
        print("Screenshot saved to screenshot_2_after_click.png")
        
        print("\nSuccessfully clicked on Digital Human template!")
    else:
        print("Could not find Digital Human button")
    
    # Keep browser open briefly
    time.sleep(2)
    browser.close()
    print("\nDone!")
