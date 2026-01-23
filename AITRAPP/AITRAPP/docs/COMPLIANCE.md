# Compliance & Regulatory Guide

## Overview

This document outlines compliance requirements and best practices for operating AITRAPP in accordance with Indian financial regulations, primarily SEBI (Securities and Exchange Board of India) guidelines.

## ⚠️ Disclaimer

**This software is provided for EDUCATIONAL PURPOSES ONLY.**

Users are solely responsible for:
- Compliance with all applicable laws and regulations
- Understanding and accepting trading risks
- Maintaining proper licenses and registrations
- Paying applicable taxes
- Following broker Terms of Service

**The authors provide NO LEGAL or FINANCIAL ADVICE and assume NO LIABILITY.**

## SEBI Regulatory Framework

### 1. Algo Trading Requirements

As per **SEBI circular on Algorithmic Trading** (SEBI/HO/MRD/DP/CIR/P/2018/81):

#### Registration Thresholds

If your trading meets ANY of these criteria, registration may be required:

- **Order-to-Trade Ratio (OTR) > 500**
- **Order Rate > specified limit** (check latest SEBI guidelines)
- **Professional/commercial algo trading**

#### Pre-Trade Risk Controls (Mandatory)

✅ **Implemented in AITRAPP**:

1. **Quantity Freeze Check**: Validates against exchange freeze limits
2. **Price Bands**: Respects circuit limits (if data available)
3. **Margin Checks**: Validates available margin before order
4. **Position Limits**: Configurable per-trade and portfolio caps
5. **Rate Limiting**: Prevents excessive order flooding

#### Post-Trade Reporting

**Broker Responsibility**: Your broker (Zerodha) handles most regulatory reporting.

**Your Responsibility**:
- Maintain audit trail of all decisions
- Document strategy logic and parameters
- Retain logs for **5 years**
- Report to broker if required

### 2. Audit Trail Requirements

SEBI mandates comprehensive audit trails for algo trading systems.

#### AITRAPP Compliance Features

✅ **Implemented**:

| Requirement | Implementation |
|-------------|----------------|
| **Order logs** | Every order stored with timestamp, strategy, rationale |
| **Decision attribution** | Signal linked to feature vector and config SHA |
| **Config versioning** | Git SHA + YAML checksum per decision |
| **Market data snapshots** | Tick and bar data retained (configurable) |
| **Risk checks** | All risk calculations logged with reasoning |
| **P&L tracking** | Trade-by-trade P&L with fees, slippage |

#### Log Retention

- **Minimum**: 90 days (default)
- **Recommended**: 5 years (SEBI requirement)
- **Format**: Structured JSON logs
- **Storage**: PostgreSQL + file logs

#### Log Contents (Per SEBI Guidelines)

Each decision/order must include:
1. Timestamp (microsecond precision)
2. Instrument identifier
3. Order details (side, quantity, price, type)
4. Strategy name and parameters
5. Market conditions (price, volume, volatility)
6. Risk calculations
7. Execution details (fill price, slippage, fees)
8. Rejection/cancellation reasons (if any)

### 3. Risk Management Framework

#### Capital Allocation

**Recommended Structure**:
- **Max 20% of total capital** in algo trading initially
- **Gradual scale-up** after proven track record
- **Emergency reserve**: Keep 30% liquid

#### Risk Limits (Non-Negotiable)

| Limit | Default | Justification |
|-------|---------|---------------|
| Per-trade risk | 0.5% | SEBI best practices |
| Portfolio heat | 2.0% | Aggregate risk cap |
| Daily loss stop | -2.5% | Hard stop for day |
| EOD square-off | 15:25 IST | Avoid overnight risk |

**These are MAXIMUM limits. Conservative traders should use lower values.**

#### Position Sizing

AITRAPP uses **risk-based position sizing**:

```
Position Size = (Capital × Risk%) / Stop Distance
```

Adjusted for:
- Lot sizes (for F&O)
- Freeze quantities
- Margin requirements
- Slippage estimates

### 4. Exchange-Specific Rules

#### NSE (National Stock Exchange)

- **Freeze Quantity**: Positions exceeding freeze limit require exchange approval
- **Price Bands**: Stocks have daily price movement limits (usually ±20%)
- **Circuit Filters**: Trading halts if limit hit
- **Auction Sessions**: Special sessions for price discovery

✅ AITRAPP validates freeze quantities before order placement.

#### BSE (Bombay Stock Exchange)

Similar rules as NSE. AITRAPP supports both exchanges.

#### F&O Segment

- **Lot Size Compliance**: All F&O orders in multiples of lot size
- **Expiry Management**: Weekly/monthly expiries
- **Physical Settlement**: Some contracts (track SEBI circulars)
- **STT/CTT**: Securities/Commodities Transaction Tax

✅ AITRAPP enforces lot size multiples and tracks expiries.

### 5. Broker Compliance (Zerodha Kite Connect)

#### API Terms of Service

**Must Comply With**:
- **Rate Limits**: 
  - Orders: 200 per second (system enforces lower)
  - Market data: 1 req/second (WebSocket preferred)
  - Historical: 60 req/minute
- **No credential sharing**: One API key per user
- **Proper error handling**: Don't hammer API on errors
- **Attribution**: Use `tag` field for order tracking

✅ AITRAPP implements:
- Exponential backoff on errors
- Rate limiting with jitter
- WebSocket for live data (not polling)
- Order tagging with strategy name

#### Kite Connect Restrictions

**Not Allowed**:
- Basket orders via API (use web for GTT/basket)
- Modifying other users' orders
- Scraping Kite web interface
- Circumventing rate limits

### 6. Tax Compliance

**Disclaimer**: Consult a tax professional. This is general information only.

#### Taxable Events

| Event | Tax Treatment (India) |
|-------|-----------------------|
| Intraday equity gains | Business income (30-40% tax slab) |
| Delivery equity gains (held <1 year) | Short-term capital gains (15%) |
| Delivery equity gains (held >1 year) | Long-term capital gains (10% above ₹1L) |
| F&O gains | Business income (30-40% slab) |

#### Record Keeping

Maintain for each trade:
- Date and time
- Instrument
- Buy/sell price
- Quantity
- Brokerage and taxes paid
- Net P&L

✅ AITRAPP stores all trade data in PostgreSQL.

#### Tax Forms

- **ITR-3**: For business income (intraday/F&O)
- **Schedule CG**: For capital gains (delivery)
- **Audit required if turnover > ₹10 Cr** (CA audit)

### 7. Data Protection & Privacy

#### Applicable Regulations

- **DPDPA 2023** (India's data protection law)
- **RBI guidelines** (if handling payment data)

#### AITRAPP Compliance

✅ **Data Minimization**: Only collects necessary trading data
✅ **No PII storage**: Instrument data, not personal info
✅ **Secure storage**: Encrypted at rest (configure DB encryption)
✅ **Access control**: Database authentication required

#### Personal Data Handling

If extending AITRAPP:
- **User consent**: Explicit opt-in for data collection
- **Data retention**: Delete after retention period
- **Right to erasure**: Implement user data deletion
- **Breach notification**: 72-hour notification requirement

### 8. Prohibited Activities

**DO NOT USE AITRAPP FOR**:

❌ Market manipulation (pump & dump, spoofing, layering)  
❌ Front-running  
❌ Insider trading  
❌ Wash trading (self-dealing)  
❌ Price rigging  
❌ Circular trading  

**All of the above are ILLEGAL and carry severe penalties.**

### 9. Monitoring & Surveillance

#### Exchange Surveillance

Exchanges monitor for:
- Unusual order patterns
- High cancellation rates
- Layering/spoofing
- Synchronized trading

**Be aware**: Automated surveillance systems flag suspicious activity.

#### Self-Monitoring

AITRAPP provides:
- Order-to-trade ratio tracking
- Cancellation rate monitoring
- Slippage analysis
- Strategy performance metrics

**Review regularly** to ensure healthy trading patterns.

### 10. Incident Reporting

#### Reportable Events

Report to broker immediately:
- **System errors** causing unintended orders
- **Runaway algo** (out-of-control ordering)
- **Fat finger errors** (large accidental orders)
- **Security breaches** affecting trading

#### Reporting Channels

- **Zerodha Support**: support@zerodha.com
- **NSE Surveillance**: As per exchange guidelines
- **SEBI**: For serious violations

### 11. Professional Registration

#### When Registration Required

If you are:
- **Portfolio Manager**: Managing others' funds
- **Investment Advisor**: Providing advice for fee
- **Research Analyst**: Publishing research
- **Broker/Sub-broker**: Facilitating trades

**Register with SEBI** in appropriate category.

#### Algo Trading License

Currently, **no separate algo license for retail traders** in India.

**May require registration if**:
- Commercial algo trading business
- High-frequency trading (HFT)
- Exceeding OTR thresholds

Check latest SEBI circulars.

### 12. Best Practices Checklist

Before going live:

- [ ] Reviewed and understood SEBI algo trading guidelines
- [ ] Confirmed compliance with broker ToS
- [ ] Set up audit trail logging (5-year retention)
- [ ] Configured risk limits (conservative initially)
- [ ] Tested kill switch and safety mechanisms
- [ ] Documented strategy logic and parameters
- [ ] Set up trade monitoring and review process
- [ ] Consulted with tax advisor on reporting
- [ ] Understood prohibited activities
- [ ] Have emergency contact (broker, exchange)

### 13. Resources & References

#### Official Guidelines

- **SEBI Algo Trading Circular**: SEBI/HO/MRD/DP/CIR/P/2018/81
- **NSE Algo Trading**: [https://www.nseindia.com/algo-trading](https://www.nseindia.com/algo-trading)
- **Zerodha Kite Connect**: [https://kite.trade](https://kite.trade)
- **SEBI Website**: [https://www.sebi.gov.in](https://www.sebi.gov.in)

#### Educational Resources

- Zerodha Varsity: [https://zerodha.com/varsity](https://zerodha.com/varsity)
- SEBI Investor Education: [https://investor.sebi.gov.in](https://investor.sebi.gov.in)

---

## Final Reminder

**This software is for educational purposes.**

Algorithmic trading carries significant risk. Only trade with capital you can afford to lose.

**When in doubt, consult professionals**: 
- Securities lawyer for regulatory questions
- Chartered accountant for tax matters
- SEBI-registered investment advisor for strategy advice

**Stay informed**: Regulations change. Subscribe to SEBI circulars and exchange notifications.

