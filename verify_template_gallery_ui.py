from playwright.sync_api import sync_playwright
import time
import json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})
    
    print("=" * 80)
    print("TEMPLATE GALLERY UI VERIFICATION")
    print("=" * 80)
    
    # Navigate to localhost:3000
    print("\n[1] Navigating to http://localhost:3000...")
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    time.sleep(2)
    
    # Take initial screenshot
    print("\n[2] Taking screenshot of gallery page...")
    page.screenshot(path='gallery_verification_1_top.png', full_page=False)
    print("    Screenshot saved: gallery_verification_1_top.png")
    
    print("\n" + "=" * 80)
    print("CHECKING UI ELEMENTS")
    print("=" * 80)
    
    # Check header branding
    print("\n[3] HEADER BRANDING CHECK:")
    
    # Check for AutoViralVid text
    if page.locator('text=AutoViralVid').count() > 0:
        print("    [OK] 'AutoViralVid' brand name found")
    else:
        print("    [FAIL] 'AutoViralVid' NOT found")
        if page.locator('text=AICapCut').count() > 0:
            print("    [ISSUE] Still showing 'AICapCut'")
    
    # Check for old branding
    if page.locator('text=AICapCut').count() > 0:
        print("    [FAIL] Old 'AICapCut' branding still present")
    
    # Check the logo/icon color
    logo_info = page.evaluate('''
        () => {
            const logo = document.querySelector('svg, [class*="logo"]');
            if (logo) {
                const style = window.getComputedStyle(logo);
                return {
                    fill: style.fill,
                    color: style.color,
                    innerHTML: logo.innerHTML ? logo.innerHTML.substring(0, 200) : null
                };
            }
            return null;
        }
    ''')
    
    if logo_info:
        print(f"    Logo fill color: {logo_info.get('fill')}")
        print(f"    Logo color: {logo_info.get('color')}")
        if logo_info.get('innerHTML'):
            if 'red' in logo_info.get('innerHTML').lower() or 'E11D48' in logo_info.get('innerHTML'):
                print("    [OK] Logo appears to use red color")
    
    # Check badge
    print("\n[4] BADGE CHECK:")
    
    badge_text = page.locator('text=智能视频创作平台')
    if badge_text.count() > 0:
        print("    [OK] Badge text '智能视频创作平台' found")
        
        # Check badge color
        badge_color = page.evaluate('''
            () => {
                const badge = document.querySelector('[class*="badge"], [class*="Badge"]');
                if (!badge) {
                    const textElement = Array.from(document.querySelectorAll('*')).find(
                        el => el.textContent.includes('智能视频创作平台')
                    );
                    if (textElement) {
                        const style = window.getComputedStyle(textElement);
                        return {
                            color: style.color,
                            backgroundColor: style.backgroundColor,
                            borderColor: style.borderColor
                        };
                    }
                }
                if (badge) {
                    const style = window.getComputedStyle(badge);
                    return {
                        color: style.color,
                        backgroundColor: style.backgroundColor,
                        borderColor: style.borderColor
                    };
                }
                return null;
            }
        ''')
        
        if badge_color:
            print(f"    Badge color: {badge_color.get('color')}")
            print(f"    Badge background: {badge_color.get('backgroundColor')}")
            
            # Check if it's red (not blue)
            color_str = str(badge_color.get('color', '')) + str(badge_color.get('backgroundColor', ''))
            if 'rgb(225, 29, 72)' in color_str or '225, 29, 72' in color_str:
                print("    [OK] Badge uses red color (#E11D48)")
            elif 'blue' in color_str.lower() or '79, 70, 229' in color_str:
                print("    [FAIL] Badge still uses blue color")
    else:
        print("    [INFO] Badge text not found")
    
    # Check template cards
    print("\n[5] TEMPLATE CARDS CHECK:")
    
    cards = page.locator('[class*="card"], button[class*="group"]').all()
    print(f"    Found {len(cards)} potential template cards")
    
    if len(cards) > 0:
        # Check first card for glassmorphism
        first_card_style = page.evaluate('''
            () => {
                const card = document.querySelector('[class*="card"], button[class*="group"]');
                if (card) {
                    const style = window.getComputedStyle(card);
                    return {
                        backdropFilter: style.backdropFilter,
                        background: style.background,
                        border: style.border,
                        boxShadow: style.boxShadow
                    };
                }
                return null;
            }
        ''')
        
        if first_card_style:
            print(f"    Card backdrop-filter: {first_card_style.get('backdropFilter')}")
            if 'blur' in str(first_card_style.get('backdropFilter')):
                print("    [OK] Cards use glassmorphism (backdrop-filter blur)")
            else:
                print("    [INFO] No backdrop-filter blur detected")
            
            print(f"    Card background: {first_card_style.get('background')[:100]}...")
    
    # Check category icons
    print("\n[6] CATEGORY ICONS CHECK:")
    
    # Look for SVG icons
    svg_icons = page.locator('svg').all()
    print(f"    Found {len(svg_icons)} SVG elements on page")
    
    # Check for emoji vs SVG in category headers
    category_sections = page.locator('[class*="category"], h2, h3').all()
    emoji_found = False
    svg_icon_found = False
    
    for section in category_sections[:10]:
        try:
            text = section.inner_text(timeout=100)
            # Check for emoji characters
            if any(ord(char) > 127 for char in text):
                if '🛍' in text or '📢' in text or '🎬' in text:
                    emoji_found = True
                    print(f"    [FAIL] Found emoji in: {text[:50]}")
        except:
            pass
    
    if not emoji_found:
        print("    [OK] No emoji icons detected in categories")
    
    if len(svg_icons) > 5:
        print("    [OK] Multiple SVG icons present (likely using SVG icons)")
    
    # Check color scheme
    print("\n[7] COLOR SCHEME CHECK:")
    
    # Get all elements with background colors
    red_elements = page.evaluate('''
        () => {
            const elements = document.querySelectorAll('*');
            let redCount = 0;
            let blueCount = 0;
            
            elements.forEach(el => {
                const style = window.getComputedStyle(el);
                const bg = style.backgroundColor;
                const color = style.color;
                const border = style.borderColor;
                
                const allColors = bg + color + border;
                
                // Check for red (#E11D48 = rgb(225, 29, 72))
                if (allColors.includes('225, 29, 72') || allColors.includes('rgb(225, 29, 72)')) {
                    redCount++;
                }
                
                // Check for blue/indigo (rgb(79, 70, 229) or similar)
                if (allColors.includes('79, 70, 229') || allColors.includes('99, 102, 241')) {
                    blueCount++;
                }
            });
            
            return { redCount, blueCount };
        }
    ''')
    
    print(f"    Elements with red accent (#E11D48): {red_elements.get('redCount')}")
    print(f"    Elements with blue/indigo accent: {red_elements.get('blueCount')}")
    
    if red_elements.get('redCount', 0) > 0:
        print("    [OK] Red accent color is being used")
    
    if red_elements.get('blueCount', 0) > 0:
        print("    [WARNING] Blue/indigo colors still present")
    
    # Check font family
    print("\n[8] FONT FAMILY CHECK:")
    
    font_family = page.evaluate('window.getComputedStyle(document.body).fontFamily')
    print(f"    Body font-family: {font_family}")
    
    if 'Plus Jakarta Sans' in font_family or 'Jakarta' in font_family:
        print("    [OK] Plus Jakarta Sans font is active")
    else:
        print("    [FAIL] Plus Jakarta Sans NOT detected")
        print(f"    Current font: {font_family}")
    
    # Scroll down to see more templates
    print("\n[9] Scrolling down to see all template cards...")
    page.evaluate('window.scrollBy(0, 600)')
    time.sleep(1)
    
    # Take screenshot after scrolling
    print("\n[10] Taking screenshot after scroll...")
    page.screenshot(path='gallery_verification_2_scrolled.png', full_page=False)
    print("     Screenshot saved: gallery_verification_2_scrolled.png")
    
    # Take full page screenshot
    print("\n[11] Taking full page screenshot...")
    page.screenshot(path='gallery_verification_full_page.png', full_page=True)
    print("     Screenshot saved: gallery_verification_full_page.png")
    
    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)
    print("\nScreenshots saved:")
    print("  1. gallery_verification_1_top.png - Initial view")
    print("  2. gallery_verification_2_scrolled.png - After scrolling")
    print("  3. gallery_verification_full_page.png - Full page view")
    
    # Keep browser open for review
    time.sleep(3)
    browser.close()
    print("\nDone!")
