#!/usr/bin/env python3
"""
Browser automation script for OpenAlgo login and MCX-only strategy management.
Uses Playwright to automate browser interactions.
"""
import asyncio
import sys
import time
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "http://127.0.0.1:5001"
LOGIN_URL = f"{BASE_URL}/auth/login"
BROKER_URL = f"{BASE_URL}/auth/broker"
STRATEGY_URL = f"{BASE_URL}/python"

# MCX strategy names (partial matches)
MCX_STRATEGIES = [
    "MCX Global Arbitrage",
    "MCX Commodity Momentum",
    "MCX Advanced",
    "MCX Elite",
    "MCX Neural",
    "MCX Quantum",
    "MCX AI Enhanced",
    "MCX Clawdbot",
    "Crude Oil",
    "Natural Gas"
]

# Non-MCX strategies to stop (NSE/equity)
NON_MCX_STRATEGIES = [
    "NIFTY",
    "BANKNIFTY",
    "Advanced ML Momentum",
    "AI Hybrid Reversion",
    "SuperTrend VWAP"
]

async def check_server_running(page):
    """Check if OpenAlgo server is running"""
    try:
        response = await page.goto(BASE_URL, wait_until="networkidle", timeout=5000)
        return response.status == 200
    except Exception as e:
        print(f"❌ Server not running: {e}")
        return False

async def login(page, username, password):
    """Login to OpenAlgo"""
    print(f"🔐 Navigating to login: {LOGIN_URL}")
    await page.goto(LOGIN_URL, wait_until="networkidle")
    
    # Check if already logged in
    if "/python" in page.url or "/dashboard" in page.url:
        print("✅ Already logged in")
        return True
    
    # Fill login form
    print("📝 Filling login form...")
    try:
        # Try different possible selectors
        username_selector = 'input[name="username"], input[name="email"], input[type="text"]'
        password_selector = 'input[name="password"], input[type="password"]'
        submit_selector = 'button[type="submit"], button:has-text("Login"), button:has-text("Sign in")'
        
        await page.fill(username_selector, username, timeout=5000)
        await page.fill(password_selector, password, timeout=5000)
        await page.click(submit_selector, timeout=5000)
        
        # Wait for redirect
        await page.wait_for_url("**/python**", timeout=10000)
        print("✅ Login successful!")
        return True
    except PlaywrightTimeoutError:
        print("⚠️  Login form not found or already logged in")
        return True
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return False

async def connect_broker(page):
    """Connect/reconnect broker"""
    print(f"🔗 Navigating to broker auth: {BROKER_URL}")
    await page.goto(BROKER_URL, wait_until="networkidle")
    
    # Look for reconnect button
    try:
        reconnect_button = page.locator('button:has-text("Reconnect"), a:has-text("Reconnect"), button:has-text("Connect")')
        if await reconnect_button.count() > 0:
            print("🔄 Clicking reconnect broker button...")
            await reconnect_button.first.click(timeout=5000)
            print("✅ Broker reconnect initiated - complete OAuth in browser")
            await asyncio.sleep(3)  # Wait for OAuth redirect
        else:
            print("✅ Broker already connected")
    except Exception as e:
        print(f"⚠️  Broker connection check: {e}")

async def manage_strategies(page, enable_mcx_only=True):
    """Enable MCX strategies and disable non-MCX strategies"""
    print(f"📊 Navigating to strategies: {STRATEGY_URL}")
    await page.goto(STRATEGY_URL, wait_until="networkidle")
    
    # Wait for strategy cards to load
    await page.wait_for_selector('.card, .strategy-card, [class*="strategy"]', timeout=10000)
    
    # Get all strategy cards
    strategy_cards = await page.locator('.card, .strategy-card, [class*="strategy"]').all()
    print(f"📋 Found {len(strategy_cards)} strategy cards")
    
    enabled_mcx = []
    stopped_non_mcx = []
    
    for card in strategy_cards:
        try:
            # Get strategy name
            name_elem = card.locator('h2, h3, .card-title, [class*="title"]').first
            strategy_name = await name_elem.text_content() if await name_elem.count() > 0 else ""
            
            if not strategy_name:
                continue
            
            # Check if MCX strategy
            is_mcx = any(mcx in strategy_name for mcx in MCX_STRATEGIES)
            is_non_mcx = any(non_mcx in strategy_name for non_mcx in NON_MCX_STRATEGIES)
            
            # Find status badge
            status_badge = card.locator('.badge-success, .badge-ghost, [class*="badge"]').first
            is_running = await status_badge.count() > 0 and "success" in (await status_badge.get_attribute("class") or "")
            
            # Find start/stop button
            start_button = card.locator('button:has-text("Start")').first
            stop_button = card.locator('button:has-text("Stop")').first
            
            if enable_mcx_only:
                if is_mcx and not is_running:
                    # Start MCX strategy
                    if await start_button.count() > 0:
                        print(f"▶️  Starting MCX: {strategy_name}")
                        await start_button.click(timeout=3000)
                        await asyncio.sleep(1)
                        enabled_mcx.append(strategy_name)
                elif is_non_mcx and is_running:
                    # Stop non-MCX strategy
                    if await stop_button.count() > 0:
                        print(f"⏹️  Stopping non-MCX: {strategy_name}")
                        await stop_button.click(timeout=3000)
                        await asyncio.sleep(1)
                        stopped_non_mcx.append(strategy_name)
        except Exception as e:
            print(f"⚠️  Error processing strategy card: {e}")
            continue
    
    print(f"\n✅ Enabled {len(enabled_mcx)} MCX strategies")
    print(f"⏹️  Stopped {len(stopped_non_mcx)} non-MCX strategies")
    
    return enabled_mcx, stopped_non_mcx

async def main():
    """Main automation flow"""
    # Get credentials from environment or use defaults
    import os
    username = os.getenv("OPENALGO_USERNAME", "sayujks0071")
    password = os.getenv("OPENALGO_PASSWORD", "Apollo@20417")
    
    async with async_playwright() as p:
        print("🌐 Launching browser...")
        browser = await p.chromium.launch(headless=False)  # Show browser
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Check server
            if not await check_server_running(page):
                print("❌ OpenAlgo server is not running on port 5001")
                print("   Start it with: cd openalgo && FLASK_PORT=5001 python app.py")
                return
            
            # Login
            if not await login(page, username, password):
                print("❌ Login failed - check credentials")
                return
            
            # Connect broker
            await connect_broker(page)
            
            # Manage strategies (MCX only)
            await manage_strategies(page, enable_mcx_only=True)
            
            print("\n✅ MCX-only setup complete!")
            print("📊 Check strategies at:", STRATEGY_URL)
            
            # Keep browser open for 10 seconds to see results
            await asyncio.sleep(10)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    print("🚀 OpenAlgo Browser Automation - MCX Only Setup")
    print("=" * 50)
    asyncio.run(main())
