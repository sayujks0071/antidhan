# Dual MCP Operations Skill

This skill enables seamless use of both Kite MCP and OpenAlgo MCP servers together for comprehensive trading operations.

## Purpose

Coordinate and leverage both MCP servers to:
- Compare data across platforms
- Execute trades on appropriate platform
- Provide unified portfolio views
- Validate data across sources
- Get comprehensive market insights

## When to Use

Use this skill when:
- Comparing holdings/positions across Kite and OpenAlgo
- Getting unified portfolio view
- Executing trades (selecting appropriate platform)
- Validating market data
- Cross-platform analysis

## MCP Server Capabilities

### Kite MCP (Hosted)
- **Broker**: Kite/Zerodha
- **Tools**: Market data, holdings, positions, orders, GTT
- **Access**: Via hosted server (no local setup)
- **Use For**: Kite-specific operations

### OpenAlgo MCP (Local)
- **Broker**: Multi-broker (Dhan, Kite, etc.)
- **Tools**: Advanced orders, option chains, strategies
- **Access**: Via local server (requires OpenAlgo running)
- **Use For**: OpenAlgo platform operations, options trading

## Usage Patterns

### Pattern 1: Unified Portfolio View

```
User: "Show me my complete portfolio"

Process:
1. Use Kite MCP: Get Kite holdings and positions
2. Use OpenAlgo MCP: Get OpenAlgo positions and holdings
3. Combine data
4. Present unified view with platform breakdown
```

### Pattern 2: Market Data Comparison

```
User: "Get quote for NIFTY from both platforms"

Process:
1. Use Kite MCP: Get NIFTY quote
2. Use OpenAlgo MCP: Get NIFTY quote
3. Compare prices
4. Highlight any differences
```

### Pattern 3: Platform-Specific Operations

```
User: "Place order on Kite" → Use Kite MCP
User: "Place order on OpenAlgo" → Use OpenAlgo MCP
User: "Place options order" → Use OpenAlgo MCP (better options support)
```

### Pattern 4: Data Validation

```
User: "Verify my RELIANCE position"

Process:
1. Use Kite MCP: Get RELIANCE position
2. Use OpenAlgo MCP: Get RELIANCE position
3. Compare quantities
4. Flag any discrepancies
```

## Implementation Guidelines

### 1. MCP Selection Logic

```python
def select_mcp(task_type, broker=None):
    if broker == "kite" or "kite" in task_type.lower():
        return "kite_mcp"
    elif "option" in task_type.lower() or "basket" in task_type.lower():
        return "openalgo_mcp"
    elif broker == "dhan" or "openalgo" in task_type.lower():
        return "openalgo_mcp"
    else:
        # Use both for comprehensive view
        return "both"
```

### 2. Error Handling

- If one MCP fails, try the other (if applicable)
- Provide clear error messages indicating which MCP failed
- Suggest alternatives when possible

### 3. Data Merging

- Combine data from both sources
- Identify platform for each item
- Highlight overlaps and differences
- Provide unified totals

## Examples

### Example 1: Get Holdings

**Request**: "Get my holdings"

**Response**:
```
📊 Your Holdings:

**Kite Platform:**
- RELIANCE: 100 shares @ ₹2,500 avg
- INFY: 50 shares @ ₹1,800 avg

**OpenAlgo Platform:**
- TCS: 75 shares @ ₹3,200 avg

**Total Portfolio Value**: ₹XXX
```

### Example 2: Compare Quotes

**Request**: "Compare RELIANCE price"

**Response**:
```
📈 RELIANCE Quote Comparison:

**Kite MCP**: ₹2,510.00
**OpenAlgo MCP**: ₹2,510.25

**Difference**: ₹0.25 (0.01%)
**Status**: ✅ Prices match closely
```

### Example 3: Execute Trade

**Request**: "Buy 100 RELIANCE on Kite"

**Response**:
```
✅ Using Kite MCP to place order...

Order Details:
- Symbol: RELIANCE
- Quantity: 100
- Action: BUY
- Platform: Kite
- Order ID: XXXXX

Status: Order placed successfully
```

## Troubleshooting

### Issue: One MCP Not Available

**Solution**: 
- Use available MCP for the operation
- Inform user which platform is being used
- Suggest checking MCP configuration if needed

### Issue: Data Mismatch

**Solution**:
- Highlight the differences
- Explain possible reasons (timing, platform differences)
- Suggest verifying with platform directly

## Best Practices

1. **Always specify platform** when using MCP tools
2. **Use both when beneficial** for comprehensive analysis
3. **Handle errors gracefully** with fallback options
4. **Provide context** about data sources
5. **Validate critical data** by comparing across platforms

## Related Skills

- `trading-operations`: General trading operations
- `risk-management`: Risk analysis using MCP data
- `trading-strategy-development`: Strategy development with MCP tools

---

**Use this skill** to leverage both MCP servers for comprehensive trading operations and analysis.
