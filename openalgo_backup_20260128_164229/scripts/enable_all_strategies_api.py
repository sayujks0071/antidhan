#!/usr/bin/env python3
"""
Enable all strategies via OpenAlgo API
Uses HTTP requests instead of browser automation
"""

import sys
import os
import re
import requests
from typing import List, Dict, Tuple

# Try both ports
PORTS = [5001, 5002]
LOGIN_CREDENTIALS = {
    'username': 'sayujks0071',
    'password': 'Apollo@20417'
}

def login(session: requests.Session, port: int) -> Tuple[bool, str]:
    """Login to OpenAlgo and return session with CSRF token"""
    login_url = f"http://127.0.0.1:{port}/auth/login"
    
    try:
        # Get login page
        response = session.get(login_url, timeout=10)
        if response.status_code != 200:
            return False, f"Failed to load login page: {response.status_code}"
        
        # Extract CSRF token
        csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        if not csrf_match:
            # Try meta tag
            csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
        
        if not csrf_match:
            return False, "CSRF token not found"
        
        csrf_token = csrf_match.group(1)
        
        # Login
        login_data = {
            'username': LOGIN_CREDENTIALS['username'],
            'password': LOGIN_CREDENTIALS['password'],
            'csrf_token': csrf_token
        }
        
        response = session.post(login_url, data=login_data, timeout=10, allow_redirects=False)
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get('status') == 'success':
                    return True, "Login successful"
            except:
                # Might be HTML redirect
                if 'python' in response.headers.get('Location', '') or response.status_code == 302:
                    return True, "Login successful (redirect)"
        
        return False, f"Login failed: {response.status_code}"
        
    except Exception as e:
        return False, f"Login error: {str(e)}"

def get_strategies(session: requests.Session, port: int) -> List[Dict]:
    """Get list of all strategies from config file or API endpoint"""
    import json
    from pathlib import Path
    
    # Try reading from config file first (most reliable)
    config_file = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                configs = json.load(f)
            
            strategies = []
            for strategy_id, strategy_info in configs.items():
                is_running = strategy_info.get('is_running', False)
                pid = strategy_info.get('pid')
                
                # Verify process is actually running if PID exists
                if pid and is_running:
                    import subprocess
                    try:
                        result = subprocess.run(['ps', '-p', str(pid)], 
                                              capture_output=True, text=True)
                        is_running = result.returncode == 0
                    except:
                        is_running = False
                
                strategies.append({
                    'id': strategy_id,
                    'name': strategy_info.get('name', strategy_id),
                    'status': 'running' if is_running else 'stopped',
                    'has_start': True,
                    'has_stop': is_running,
                    'is_running': is_running
                })
            
            if strategies:
                return strategies
        except Exception as e:
            print(f"   ⚠️  Error reading config file: {e}")
    
    # Fallback: Try JSON API endpoint
    status_url = f"http://127.0.0.1:{port}/python/status"
    
    try:
        response = session.get(status_url, timeout=10)
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and 'strategies' in data:
                    strategies = []
                    for strategy_id, strategy_info in data['strategies'].items():
                        strategies.append({
                            'id': strategy_id,
                            'name': strategy_info.get('name', strategy_id),
                            'status': strategy_info.get('status', 'unknown'),
                            'has_start': True,
                            'has_stop': strategy_info.get('is_running', False),
                            'is_running': strategy_info.get('is_running', False)
                        })
                    return strategies
            except:
                pass
    except:
        pass
    
    # Fallback to HTML parsing
    strategy_url = f"http://127.0.0.1:{port}/python"
    
    try:
        response = session.get(strategy_url, timeout=10)
        if response.status_code != 200:
            return []
        
        html = response.text
        strategies = []
        
        # Find all startStrategy calls in onclick handlers (more flexible pattern)
        start_strategy_patterns = [
            r"startStrategy\(['\"]([^'\"]+)['\"]\)",
            r"startStrategy\(([^)]+)\)",
            r'onclick=["\']startStrategy\(["\']([^"\']+)["\']\)',
            r"onclick=['\"]startStrategy\(['\"]([^'\"]+)['\"]\)",
        ]
        
        strategy_ids = set()
        for pattern in start_strategy_patterns:
            matches = re.findall(pattern, html, re.I)
            strategy_ids.update(matches)
        
        # Also look for stopStrategy calls to identify running strategies
        stop_strategy_patterns = [
            r"stopStrategy\(['\"]([^'\"]+)['\"]\)",
            r"stopStrategy\(([^)]+)\)",
            r'onclick=["\']stopStrategy\(["\']([^"\']+)["\']\)',
        ]
        
        running_ids = set()
        for pattern in stop_strategy_patterns:
            matches = re.findall(pattern, html, re.I)
            running_ids.update(matches)
        
        # Also try to find strategy IDs in data attributes
        data_id_patterns = [
            r'data-strategy-id=["\']([^"\']+)["\']',
            r'data-id=["\']([^"\']+)["\']',
            r'id=["\']strategy-([^"\']+)["\']',
        ]
        
        for pattern in data_id_patterns:
            matches = re.findall(pattern, html, re.I)
            strategy_ids.update(matches)
        
        # For each strategy ID, try to extract name and status
        for strategy_id in strategy_ids:
            try:
                # Find the card/container for this strategy
                # Look for onclick="startStrategy('ID')" and extract surrounding HTML
                pattern = rf'(?:<[^>]+onclick=["\']startStrategy\(["\']{re.escape(strategy_id)}["\']\)["\'][^>]*>.*?</[^>]+>)|(?:<[^>]+>.*?onclick=["\']startStrategy\(["\']{re.escape(strategy_id)}["\']\)["\']'
                
                # Try to find strategy name - look for card-title or h2/h3/h4 near the button
                name_patterns = [
                    rf'<[^>]*class=["\'][^"\']*card-title[^"\']*["\'][^>]*>([^<]+)</',
                    rf'<h[234][^>]*>([^<]+)</h[234]>',
                    rf'<[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>([^<]+)</',
                ]
                
                strategy_name = f"Strategy {strategy_id[:8]}"
                for name_pattern in name_patterns:
                    # Search in a window around the strategy ID
                    id_pos = html.find(strategy_id)
                    if id_pos > 0:
                        window_start = max(0, id_pos - 500)
                        window_end = min(len(html), id_pos + 500)
                        window = html[window_start:window_end]
                        
                        match = re.search(name_pattern, window, re.I)
                        if match:
                            strategy_name = match.group(1).strip()
                            break
                
                # Check status - look for badge classes
                status_text = ""
                badge_patterns = [
                    rf'<[^>]*class=["\'][^"\']*badge-success[^"\']*["\'][^>]*>([^<]+)</',
                    rf'<[^>]*class=["\'][^"\']*badge-ghost[^"\']*["\'][^>]*>([^<]+)</',
                    rf'<[^>]*class=["\'][^"\']*badge-error[^"\']*["\'][^>]*>([^<]+)</',
                ]
                
                id_pos = html.find(strategy_id)
                if id_pos > 0:
                    window_start = max(0, id_pos - 300)
                    window_end = min(len(html), id_pos + 300)
                    window = html[window_start:window_end]
                    
                    for badge_pattern in badge_patterns:
                        match = re.search(badge_pattern, window, re.I)
                        if match:
                            status_text = match.group(1).strip()
                            break
                
                is_running = strategy_id in running_ids or 'running' in status_text.lower() or 'success' in status_text.lower()
                
                strategies.append({
                    'id': strategy_id,
                    'name': strategy_name,
                    'status': status_text,
                    'has_start': True,
                    'has_stop': strategy_id in running_ids,
                    'is_running': is_running
                })
                
            except Exception as e:
                # If extraction fails, still add the strategy with minimal info
                strategies.append({
                    'id': strategy_id,
                    'name': f"Strategy {strategy_id[:8]}",
                    'status': 'unknown',
                    'has_start': True,
                    'has_stop': strategy_id in running_ids,
                    'is_running': strategy_id in running_ids
                })
        
        return strategies
        
    except Exception as e:
        print(f"Error getting strategies: {e}")
        import traceback
        traceback.print_exc()
        return []

def start_strategy(session: requests.Session, port: int, strategy_id: str) -> Tuple[bool, str]:
    """Start a strategy via API"""
    start_url = f"http://127.0.0.1:{port}/python/start/{strategy_id}"
    
    try:
        # Get CSRF token from login page or strategy page
        csrf_token = None
        for url in [f"http://127.0.0.1:{port}/auth/login", f"http://127.0.0.1:{port}/python"]:
            try:
                response = session.get(url, timeout=5)
                # Try meta tag first
                csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
                if not csrf_match:
                    # Try form input
                    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
                if csrf_match:
                    csrf_token = csrf_match.group(1)
                    break
            except:
                continue
        
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        if csrf_token:
            headers['X-CSRFToken'] = csrf_token
            # Also include in form data
            data = {'csrf_token': csrf_token}
        else:
            data = {}
        
        response = session.post(start_url, headers=headers, data=data, timeout=10, allow_redirects=False)
        
        # Check for redirect (might indicate success)
        if response.status_code in [302, 303, 307]:
            return True, "Strategy started (redirected)"
        
        if response.status_code == 200:
            # Check if it's JSON
            content_type = response.headers.get('Content-Type', '')
            if 'json' in content_type:
                try:
                    data = response.json()
                    if data.get('success') or 'started' in data.get('message', '').lower():
                        return True, data.get('message', 'Strategy started')
                except:
                    pass
            # Check if HTML response contains success indicators
            if 'started' in response.text.lower() or 'success' in response.text.lower():
                return True, "Strategy started"
        
        # Rate limit handling
        if response.status_code == 429:
            return False, f"Rate limit exceeded"
        
        return False, f"Failed: {response.status_code} - {response.text[:200]}"
        
    except Exception as e:
        return False, f"Error: {str(e)}"

def main():
    """Main function to enable all strategies"""
    # Get all strategies from config file first (no login needed)
    print(f"\n📋 Loading strategies from config file...")
    strategies = get_strategies(None, None)  # Pass None since we're reading from file
    
    if not strategies:
        print("   ⚠️  No strategies found")
        return False
    
    print(f"   Found {len(strategies)} strategies\n")
    
    # Filter stopped strategies
    stopped_strategies = [s for s in strategies if not s['is_running'] and s['has_start']]
    running_strategies = [s for s in strategies if s['is_running']]
    
    print(f"📊 Status Summary:")
    print(f"   ✅ Running: {len(running_strategies)}")
    print(f"   ⏸️  Stopped: {len(stopped_strategies)}")
    print(f"   📋 Total: {len(strategies)}\n")
    
    if not stopped_strategies:
        print("✅ All strategies are already running!")
        return True
    
    # Now login to start strategies
    print(f"\n🔐 Logging in to start strategies...")
    session = requests.Session()
    logged_in = False
    working_port = None
    
    for port in PORTS:
        print(f"   Trying port {port}...")
        success, message = login(session, port)
        if success:
            logged_in = True
            working_port = port
            print(f"   ✅ Logged in on port {port}")
            break
        else:
            print(f"   ⚠️  {message}")
    
    if not logged_in:
        print("\n❌ Failed to login - cannot start strategies via API")
        print("   You may need to start them manually via the web UI")
        return False
    
    # Enable all stopped strategies
    print(f"\n🚀 Starting {len(stopped_strategies)} stopped strategies...\n")
    
    enabled_count = 0
    failed_count = 0
    
    for i, strategy in enumerate(stopped_strategies, 1):
        print(f"[{i}/{len(stopped_strategies)}] {strategy['name']} ({strategy['id'][:50]}...)")
        
        success, message = start_strategy(session, working_port, strategy['id'])
        
        if success:
            print(f"   ✅ {message}")
            enabled_count += 1
        else:
            if "rate limit" in message.lower() or "429" in message:
                print(f"   ⚠️  Rate limited - waiting 10 seconds...")
                import time
                time.sleep(10)
                # Retry once
                success, message = start_strategy(session, working_port, strategy['id'])
                if success:
                    print(f"   ✅ {message} (after retry)")
                    enabled_count += 1
                else:
                    print(f"   ❌ {message} (retry failed)")
                    failed_count += 1
            else:
                print(f"   ❌ {message}")
                failed_count += 1
        
        # Delay between requests to avoid rate limits (longer delay)
        import time
        time.sleep(5)  # 5 second delay between requests to avoid rate limits
    
    # Final summary
    print(f"\n{'='*60}")
    print(f"📊 Final Summary:")
    print(f"   ✅ Enabled: {enabled_count}")
    print(f"   ✅ Already Running: {len(running_strategies)}")
    print(f"   ❌ Failed: {failed_count}")
    print(f"   📋 Total: {len(strategies)}")
    print(f"{'='*60}\n")
    
    return enabled_count > 0

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
