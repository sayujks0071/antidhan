import urllib.request
import urllib.error
import json
import http.cookiejar
import time

HOST = 'http://127.0.0.1:5002'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [('User-Agent', 'Mozilla/5.0')]

# Login
opener.open(HOST + '/auth/autologin/9b16ad5b50551924', timeout=10)

# Get CSRF token
resp2 = opener.open(HOST + '/auth/csrf-token', timeout=10)
csrf_token = json.loads(resp2.read()).get('csrf_token', '')
print('CSRF OK: ' + csrf_token[:20] + '...')

strategies = [
    'ai_hybrid_reliance_20260203095647','ai_hybrid_reliance','supertrend_vwap_nifty',
    'keltner_adx_trend','stochastic_macd_momentum','mean_reversion_pro',
    'faber_trend_following','rsi2_pullback','bollinger_mean_reversion',
    'dual_momentum_proxy','time_series_momentum',
    'oc_pcr_nifty','oc_oi_wall_banknifty','oc_straddle_momentum_nifty',
    'oc_volume_surge_banknifty','oc_oi_shift_nifty','oc_iron_condor_nifty',
    'oc_short_strangle_banknifty','oc_bull_spread_nifty','oc_bear_spread_banknifty',
    'oc_iron_butterfly_sensex','oc_oi_strangle_nifty','mcx_crudeoil_momentum'
]

def call(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('X-CSRFToken', csrf_token)
    try:
        r = opener.open(req, timeout=20)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'status': 'error', 'message': e.read().decode()[:100]}
    except Exception as ex:
        return {'status': 'error', 'message': str(ex)}

print('Stopping all strategies...')
stopped = 0
for sid in strategies:
    r = call(HOST + '/python/stop/' + sid, {})
    msg = r.get('message', '')
    if 'stopped' in msg.lower() or r.get('status') == 'success':
        stopped += 1
        print('  STOP: ' + sid)
    time.sleep(0.2)
print('Stopped ' + str(stopped) + '. Waiting 3s...')
time.sleep(3)

print('Restarting with force=True...')
started = []
skipped = []
for sid in strategies:
    r = call(HOST + '/python/start/' + sid, {'force': True})
    msg = r.get('message', '')[:70]
    if r.get('status') == 'success':
        started.append(sid)
        print('  OK ' + sid + ': ' + msg)
    else:
        skipped.append(sid)
        print('  SKIP ' + sid + ': ' + msg)
    time.sleep(0.5)

print('=== DONE === Started:' + str(len(started)) + ' Skipped:' + str(len(skipped)))
