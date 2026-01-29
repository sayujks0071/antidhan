# login

Fast-start morning login checklist for OpenAlgo, Kite MCP, and broker sessions.

## Run

1. **Kite MCP (for positions/orders via MCP):**
   - If you use Kite MCP (`get_positions`, `get_orders`, etc.), run the **Kite MCP login** tool first.
   - Complete the browser login at the link the tool returns; then Kite MCP calls will work until the session expires.
2. Check app status and port:
   - `lsof -i :5001`
3. If not running, start OpenAlgo:
   - `FLASK_PORT=5001 python3 -m openalgo.app`
4. Verify broker session via UI:
   - Go to `http://localhost:5001`
   - Log in and confirm broker status is **Connected**
5. Validate API key (if needed):
   - Open **Settings** → **API Keys**
   - Ensure `OPENALGO_APIKEY` matches the strategy config (and OpenAlgo MCP uses the same key in `.cursor/mcp.json`).
6. Confirm strategies are enabled:
   - Open **Strategies** and verify expected strategies are **On**
7. Check logs for errors:
   - `tail -n 200 logs/openalgo.log | rg -i "error|critical|auth failed|order rejected"`

## If errors

- **Kite MCP:** Session errors or "log in first" → run the Kite MCP login tool again and complete the browser flow.
- Authentication failure: re-login in broker UI and re-check API key.
- Port busy: stop the existing process and restart OpenAlgo.
- Missing logs: ensure `logs/` exists and the app has write permissions.
