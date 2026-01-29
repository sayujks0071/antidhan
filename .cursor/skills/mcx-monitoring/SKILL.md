# MCX Strategy Monitoring Skill

This skill enables comprehensive monitoring of MCX commodity trading strategies using both Kite MCP and OpenAlgo MCP.

## Purpose

Monitor MCX strategies by:
- Checking strategy execution status
- Monitoring MCX positions across platforms
- Verifying orders and trades
- Providing unified status reports
- Alerting on discrepancies

## When to Use

Use this skill when:
- MCX strategies are running
- Need to check MCX position status
- Verify strategy execution
- Monitor MCX trades
- Compare positions across platforms

## MCP Server Usage

### Kite MCP (Hosted)
- Get MCX positions and holdings
- Check MCX order status
- Get MCX market data

### OpenAlgo MCP (Local)
- Get strategy execution status
- Check order book for MCX orders
- Get position book for MCX symbols
- View trade book for MCX trades

## Monitoring Workflow

### 1. Get MCX Positions

**From Kite MCP**:
```
"Using Kite MCP, get my MCX positions"
"Show my MCX holdings using Kite MCP"
```

**From OpenAlgo MCP**:
```
"Using OpenAlgo MCP, get my position book and filter for MCX symbols"
"Show MCX positions using OpenAlgo MCP"
```

### 2. Check Strategy Status

**MCX Strategies**:
- MCX Global Arbitrage
- MCX Commodity Momentum
- MCX Advanced Strategy
- MCX Elite Strategy
- MCX Neural Strategy

**Check via OpenAlgo MCP**:
```
"Using OpenAlgo MCP, get my order book and show MCX orders"
"Get trade book using OpenAlgo MCP for MCX symbols"
```

### 3. Compare and Analyze

- Compare positions from both platforms
- Identify discrepancies
- Check for open orders
- Verify strategy execution

## MCX Symbol Reference

Common MCX commodity symbols:
- **GOLD**: GOLDM, GOLDGUINEA
- **SILVER**: SILVERM
- **CRUDE OIL**: CRUDEOIL
- **NATURAL GAS**: NATURALGAS
- **COPPER**: COPPER

## Example Monitoring Queries

### Get MCX Status
```
"Monitor my MCX strategies using both MCP servers"
"Show me MCX positions from Kite and OpenAlgo"
```

### Check Specific Strategy
```
"Check MCX Global Arbitrage status using OpenAlgo MCP"
"Show MCX Global Arbitrage positions from Kite MCP"
```

### Monitor Positions
```
"Get my MCX commodity positions using both platforms"
"Compare MCX positions between Kite and OpenAlgo"
```

## Output Format

Provide unified reports with:
- MCX strategy execution status
- Current MCX positions
- Open MCX orders
- Recent MCX trades
- P&L summary
- Platform comparison
- Action items

## Best Practices

1. **Use both MCPs** for comprehensive monitoring
2. **Filter for MCX** symbols/exchange
3. **Compare data** across platforms
4. **Alert on discrepancies**
5. **Provide actionable insights**

---

**Use this skill** to monitor MCX strategies comprehensively using both MCP servers.
