from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})
    
    # Navigate to localhost:3000
    print("Navigating to http://localhost:3000...")
    page.goto('http://localhost:3000')
    
    # Wait 3 seconds for the page to load
    print("Waiting 3 seconds for page to load...")
    time.sleep(3)
    page.wait_for_load_state('networkidle')
    
    # Find the Digital Human button
    print("\nLooking for Digital Human (数字人口播) template card...")
    digital_human_button = page.locator('button:has-text("数字人口播")')
    
    if digital_human_button.count() > 0:
        print(f"Found Digital Human button!")
        
        # Scroll the button into view
        digital_human_button.first.scroll_into_view_if_needed()
        time.sleep(0.5)
        
        # Click the button
        print("Clicking on Digital Human template card...")
        digital_human_button.first.click()
        
        # Wait 2 seconds after clicking
        print("Waiting 2 seconds after click...")
        time.sleep(2)
        page.wait_for_load_state('networkidle')
        
        # Take screenshot
        print("\nTaking screenshot of the form...")
        page.screenshot(path='digital_human_form_verification.png', full_page=True)
        print("Screenshot saved to digital_human_form_verification.png")
        
        # Verify the form fields
        print("\n=== Verifying Digital Human Form Fields ===")
        
        # Check for template dropdown showing "数字人口播"
        template_dropdown = page.locator('text=数字人口播').first
        if template_dropdown.is_visible():
            print("[OK] Template dropdown shows '数字人口播'")
        
        # Check for "音频文件" (Audio File)
        if page.locator('text=音频文件').count() > 0:
            print("[OK] Found '音频文件' (Audio File) field")
        else:
            print("[MISSING] '音频文件' (Audio File) field")
        
        # Check for "声音模式" (Voice Mode)
        if page.locator('text=声音模式').count() > 0:
            print("[OK] Found '声音模式' (Voice Mode) field")
        else:
            print("[MISSING] '声音模式' (Voice Mode) field")
        
        # Check for "动作描述" (Motion Prompt)
        if page.locator('text=动作描述').count() > 0:
            print("[OK] Found '动作描述' (Motion Prompt) field")
        else:
            print("[MISSING] '动作描述' (Motion Prompt) field")
        
        # Get all visible text to help debug
        print("\n=== All form field labels found ===")
        labels = page.locator('label, [class*="label"]').all()
        for label in labels[:20]:
            try:
                text = label.inner_text(timeout=100)
                if text.strip():
                    print(f"  - {text.strip()}")
            except:
                pass
        
        print("\nVerification complete!")
    else:
        print("ERROR: Could not find Digital Human button")
    
    # Keep browser open for review
    time.sleep(3)
    browser.close()
    print("\nDone!")
