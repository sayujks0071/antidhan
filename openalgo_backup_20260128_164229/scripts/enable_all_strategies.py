#!/usr/bin/env python3
"""
Enable all strategies via browser automation
Uses Playwright to interact with OpenAlgo web UI
"""

import asyncio
from playwright.async_api import async_playwright
import sys

async def enable_all_strategies():
    """Enable all stopped strategies via browser automation"""
    
    # Try both ports
    ports = [5001, 5002]
    base_url = None
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Try to login and navigate to strategy page
        for port in ports:
            try:
                print(f"Trying port {port}...")
                login_url = f"http://127.0.0.1:{port}/auth/login"
                await page.goto(login_url, wait_until="networkidle", timeout=10000)
                
                # Check if we're on login page
                if "login" in page.url.lower():
                    print(f"Login required on port {port}")
                    
                    # Fill login form
                    username_field = page.locator('input[placeholder*="username" i], input[name="username"]').first
                    password_field = page.locator('input[placeholder*="password" i], input[name="password"]').first
                    signin_button = page.locator('button:has-text("Sign in"), button[type="submit"]').first
                    
                    if await username_field.is_visible(timeout=5000):
                        await username_field.fill("sayujks0071")
                        await password_field.fill("Apollo@20417")
                        await signin_button.click()
                        await page.wait_for_timeout(2000)
                
                # Navigate to strategy page
                strategy_url = f"http://127.0.0.1:{port}/python"
                await page.goto(strategy_url, wait_until="networkidle", timeout=10000)
                
                # Check if we successfully reached strategy page
                if "python" in page.url or "strategy" in page.url.lower():
                    print(f"✅ Successfully accessed strategy page on port {port}")
                    base_url = f"http://127.0.0.1:{port}"
                    break
                else:
                    print(f"⚠️  Port {port} redirected, trying next port...")
                    
            except Exception as e:
                print(f"⚠️  Port {port} failed: {e}")
                continue
        
        if not base_url:
            print("❌ Could not access strategy page on any port")
            await browser.close()
            return False
        
        # Wait for strategy cards to load
        print("\n📋 Loading strategies...")
        await page.wait_for_selector('.card, .strategy-card, [class*="card"]', timeout=10000)
        await page.wait_for_timeout(2000)
        
        # Find all strategy cards
        strategy_cards = await page.locator('.card, .strategy-card, [class*="card"]').all()
        print(f"Found {len(strategy_cards)} strategy cards")
        
        enabled_count = 0
        already_running = 0
        error_count = 0
        
        # Process each strategy
        for i, card in enumerate(strategy_cards):
            try:
                # Get strategy name
                name_elem = card.locator('.card-title, h2, h3, [class*="title"]').first
                strategy_name = await name_elem.text_content() if await name_elem.count() > 0 else f"Strategy {i+1}"
                strategy_name = strategy_name.strip() if strategy_name else f"Strategy {i+1}"
                
                # Check status
                status_badge = card.locator('.badge-success, .badge-ghost, .badge-error, [class*="badge"]').first
                status_text = ""
                if await status_badge.count() > 0:
                    status_text = await status_badge.text_content()
                    status_text = status_text.strip() if status_text else ""
                
                # Check if already running
                start_button = card.locator('button:has-text("Start"), button:has-text("start")').first
                stop_button = card.locator('button:has-text("Stop"), button:has-text("stop")').first
                
                has_start = await start_button.is_visible(timeout=1000)
                has_stop = await stop_button.is_visible(timeout=1000)
                
                print(f"\n[{i+1}/{len(strategy_cards)}] {strategy_name}")
                print(f"   Status: {status_text}")
                
                if has_stop or "running" in status_text.lower() or "success" in status_text.lower():
                    print(f"   ✅ Already running")
                    already_running += 1
                elif has_start:
                    print(f"   🚀 Starting strategy...")
                    try:
                        await start_button.click()
                        await page.wait_for_timeout(2000)
                        
                        # Wait for status change
                        await page.wait_for_timeout(3000)
                        
                        # Verify it started
                        new_status = card.locator('.badge-success').first
                        if await new_status.is_visible(timeout=5000):
                            print(f"   ✅ Successfully started!")
                            enabled_count += 1
                        else:
                            print(f"   ⚠️  Started but status unclear")
                            enabled_count += 1
                    except Exception as e:
                        print(f"   ❌ Failed to start: {e}")
                        error_count += 1
                elif "error" in status_text.lower():
                    print(f"   ⚠️  Has error - may need API configuration")
                    error_count += 1
                else:
                    print(f"   ⚠️  Unknown state")
                    
            except Exception as e:
                print(f"   ❌ Error processing strategy: {e}")
                error_count += 1
        
        # Summary
        print(f"\n{'='*60}")
        print(f"📊 Summary:")
        print(f"   ✅ Enabled: {enabled_count}")
        print(f"   ✅ Already Running: {already_running}")
        print(f"   ⚠️  Errors/Issues: {error_count}")
        print(f"   📋 Total: {len(strategy_cards)}")
        print(f"{'='*60}\n")
        
        # Keep browser open for a few seconds to see results
        await page.wait_for_timeout(5000)
        await browser.close()
        
        return enabled_count > 0 or already_running > 0

if __name__ == "__main__":
    try:
        success = asyncio.run(enable_all_strategies())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
