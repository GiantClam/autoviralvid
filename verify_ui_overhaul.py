from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})
    
    print("=" * 80)
    print("UI OVERHAUL VERIFICATION")
    print("=" * 80)
    
    # Navigate to localhost:3000
    print("\n1. Navigating to http://localhost:3000...")
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    time.sleep(2)
    
    # Take screenshot of landing page (top section)
    print("\n2. Taking screenshot of landing page (hero section)...")
    page.screenshot(path='ui_verification_1_hero.png', full_page=False)
    print("   Screenshot saved: ui_verification_1_hero.png")
    
    # Check for key elements in hero section
    print("\n3. Checking hero section elements...")
    
    # Check for navbar
    if page.locator('nav').count() > 0:
        print("   [OK] Navbar found")
    
    # Check for logo/brand
    if page.locator('text=AutoViralVid').count() > 0:
        print("   [OK] 'AutoViralVid' brand text found")
    else:
        print("   [MISSING] 'AutoViralVid' brand text")
    
    # Check for hero heading
    hero_headings = [
        'text=Turn Ideas into Viral Hits',
        'text=Viral Hits',
        'text=Automatically'
    ]
    for heading in hero_headings:
        if page.locator(heading).count() > 0:
            print(f"   [OK] Hero heading found: {heading}")
            break
    
    # Check for CTA button
    cta_buttons = page.locator('button, a').all()
    print(f"   Found {len(cta_buttons)} buttons/links on page")
    
    # Scroll down to see features section
    print("\n4. Scrolling down to Features section...")
    page.evaluate('window.scrollBy(0, 800)')
    time.sleep(1)
    
    # Take screenshot of features section
    print("\n5. Taking screenshot of Features section...")
    page.screenshot(path='ui_verification_2_features.png', full_page=False)
    print("   Screenshot saved: ui_verification_2_features.png")
    
    # Check for features
    if page.locator('text=Features').count() > 0 or page.locator('text=功能').count() > 0:
        print("   [OK] Features section found")
    
    # Scroll down more to see showcase
    print("\n6. Scrolling down to Showcase section...")
    page.evaluate('window.scrollBy(0, 800)')
    time.sleep(1)
    
    # Take screenshot of showcase section
    print("\n7. Taking screenshot of Showcase section...")
    page.screenshot(path='ui_verification_3_showcase.png', full_page=False)
    print("   Screenshot saved: ui_verification_3_showcase.png")
    
    # Scroll to bottom for footer
    print("\n8. Scrolling to footer...")
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(1)
    
    # Take screenshot of footer
    print("\n9. Taking screenshot of Footer section...")
    page.screenshot(path='ui_verification_4_footer.png', full_page=False)
    print("   Screenshot saved: ui_verification_4_footer.png")
    
    # Take full page screenshot
    print("\n10. Taking full page screenshot...")
    page.screenshot(path='ui_verification_full_page.png', full_page=True)
    print("    Screenshot saved: ui_verification_full_page.png")
    
    # Check computed styles for color scheme
    print("\n11. Checking color scheme...")
    
    # Get background color
    bg_color = page.evaluate('window.getComputedStyle(document.body).backgroundColor')
    print(f"    Body background color: {bg_color}")
    
    # Check for red color usage (#E11D48 or similar)
    page_html = page.content()
    if '#E11D48' in page_html or 'rgb(225, 29, 72)' in page_html or 'rose-600' in page_html:
        print("    [OK] Red accent color (#E11D48) found in HTML")
    else:
        print("    [INFO] Checking for red colors in styles...")
    
    # Check font family
    font_family = page.evaluate('window.getComputedStyle(document.body).fontFamily')
    print(f"    Body font family: {font_family}")
    if 'Plus Jakarta Sans' in font_family or 'Jakarta' in font_family:
        print("    [OK] Plus Jakarta Sans font detected")
    else:
        print("    [INFO] Font family: {font_family}")
    
    # Check for glassmorphism effects (backdrop-filter)
    nav_backdrop = page.evaluate('''
        () => {
            const nav = document.querySelector('nav');
            if (nav) {
                const style = window.getComputedStyle(nav);
                return {
                    backdropFilter: style.backdropFilter,
                    background: style.background,
                    position: style.position
                };
            }
            return null;
        }
    ''')
    
    if nav_backdrop:
        print(f"\n12. Navbar styling:")
        print(f"    Position: {nav_backdrop.get('position')}")
        print(f"    Backdrop filter: {nav_backdrop.get('backdropFilter')}")
        print(f"    Background: {nav_backdrop.get('background')[:100]}...")
        
        if 'blur' in str(nav_backdrop.get('backdropFilter')):
            print("    [OK] Glassmorphism effect (backdrop-filter blur) detected on navbar")
        if nav_backdrop.get('position') in ['fixed', 'sticky']:
            print("    [OK] Navbar is floating (fixed/sticky position)")
    
    print("\n" + "=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)
    print("\nPlease review the screenshots:")
    print("  - ui_verification_1_hero.png")
    print("  - ui_verification_2_features.png")
    print("  - ui_verification_3_showcase.png")
    print("  - ui_verification_4_footer.png")
    print("  - ui_verification_full_page.png")
    
    # Keep browser open for review
    time.sleep(3)
    browser.close()
    print("\nDone!")
