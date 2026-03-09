from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})
    
    # Navigate to localhost:3000
    print("Navigating to http://localhost:3000...")
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    time.sleep(2)
    
    # Take initial screenshot
    print("\nTaking initial screenshot...")
    page.screenshot(path='screenshot_1_initial.png', full_page=True)
    print("Screenshot saved to screenshot_1_initial.png")
    
    # Find the Digital Human button and scroll it into view
    print("\nLooking for Digital Human (数字人口播) button...")
    
    digital_human_button = page.locator('button:has-text("数字人口播")')
    
    if digital_human_button.count() > 0:
        print(f"Found {digital_human_button.count()} button(s) with '数字人口播'")
        
        # Scroll the button into view
        print("Scrolling button into view...")
        digital_human_button.first.scroll_into_view_if_needed()
        time.sleep(1)
        
        # Take screenshot with button visible
        print("\nTaking screenshot with Digital Human button visible...")
        page.screenshot(path='screenshot_1b_button_visible.png', full_page=True)
        print("Screenshot saved to screenshot_1b_button_visible.png")
        
        # Get the button text to confirm
        button_text = digital_human_button.first.inner_text()
        print(f"\nButton text: {button_text}")
        
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
    time.sleep(3)
    browser.close()
    print("\nDone!")
