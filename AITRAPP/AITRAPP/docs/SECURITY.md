# Security & Compliance Guide

## ⚠️ CRITICAL: Educational Software Disclaimer

**THIS SOFTWARE IS PROVIDED FOR EDUCATIONAL PURPOSES ONLY.**

- This system is designed to teach algorithmic trading concepts
- Always comply with SEBI regulations and broker Terms of Service
- Never trade with capital you cannot afford to lose
- Past performance does not guarantee future results
- The authors assume **NO LIABILITY** for any financial losses

## Security Best Practices

### 1. API Credentials

**NEVER commit credentials to version control.**

- Store `KITE_API_KEY`, `KITE_API_SECRET`, and `KITE_ACCESS_TOKEN` in `.env` file
- Add `.env` to `.gitignore`
- Use environment variables or secure secrets management (e.g., AWS Secrets Manager, HashiCorp Vault)
- Rotate access tokens regularly
- Limit API key permissions to minimum required

### 2. Database Security

- Use strong passwords for PostgreSQL
- Restrict database access to localhost or VPN
- Enable SSL/TLS for database connections in production
- Regular backups (encrypted at rest)
- Implement row-level security if multi-tenant

### 3. API Security

- Use JWT tokens for API authentication
- Implement rate limiting (already included)
- Enable HTTPS in production (use Let's Encrypt)
- Whitelist allowed origins in CORS policy
- Log all API access for audit trail

### 4. Network Security

- Run behind a firewall
- Use VPN for remote access
- Expose only necessary ports:
  - 8000 (API, internal only)
  - 3000 (Dashboard, internal only)
  - 443 (HTTPS, if exposing externally)
- Consider running in a DMZ or isolated network

### 5. Kill Switch & Risk Controls

The system includes multiple layers of protection:

#### Kill Switch
- **Location**: Dashboard + API endpoint `/flatten`
- **Action**: Immediately closes all positions and pauses trading
- **Access**: Should be physically accessible (not requiring network)
- **Test regularly**: Weekly kill switch drills

#### Risk Limits (Non-negotiable)
- **Per-trade risk**: Default 0.5% of capital (configurable)
- **Portfolio heat**: Max 2.0% aggregate risk (hard limit)
- **Daily loss stop**: -2.5% hard stop (system pauses)
- **EOD square-off**: 15:25 IST automatic flatten

#### Circuit Breakers
- Position size caps (lot multiples)
- Freeze quantity compliance
- Margin checks before entry
- Rate limiting on order placement

### 6. Audit & Logging

All system actions are logged with:
- Timestamp (ISO format)
- Decision rationale
- Feature vectors used
- Config SHA (for reproducibility)
- P&L attribution

**Log Retention**: 90 days minimum (configurable)

**Log Security**:
- Structured JSON logs
- Write to immutable storage
- Regular log review for anomalies
- Alert on critical events (daily loss limit, kill switch)

### 7. Paper Mode (Default)

**Always start in PAPER mode.**

- Paper mode simulates orders without real execution
- Switching to LIVE requires explicit confirmation
- LIVE mode requires typing: `CONFIRM LIVE TRADING`
- System defaults to PAPER on restart

### 8. Data Protection

- Do not log sensitive data (API keys, tokens)
- Mask credentials in logs (implemented)
- Comply with data protection regulations (GDPR, if applicable)
- User data anonymization where possible

### 9. Dependency Management

- Pin dependency versions in `requirements.txt`
- Regular security audits: `pip-audit` or `safety check`
- Update dependencies for security patches
- Review changes in kiteconnect library updates

### 10. Incident Response Plan

In case of security breach or system failure:

1. **Immediate Actions**:
   - Activate kill switch (flatten all positions)
   - Pause trading
   - Revoke API tokens
   - Isolate affected systems

2. **Investigation**:
   - Review audit logs
   - Identify root cause
   - Document timeline

3. **Remediation**:
   - Patch vulnerabilities
   - Rotate credentials
   - Restore from backups if needed

4. **Post-Mortem**:
   - Document lessons learned
   - Update runbook
   - Improve monitoring

## SEBI Compliance (India)

### Algo Trading Registration

- Ensure compliance with SEBI circular on algo trading
- Register with exchange if required (threshold-based)
- Maintain audit trail for 5 years
- Report to broker/exchange as required

### Risk Management Framework

As per SEBI guidelines:

- **Pre-trade risk checks**: Implemented (position size, margin)
- **Order throttling**: Rate limiting implemented
- **Freeze quantity compliance**: Validated before order
- **Order-to-trade ratio monitoring**: Log and review
- **Post-trade analysis**: P&L attribution and review

### Audit Requirements

- **System logs**: Retain for 5 years
- **Order trail**: Complete audit log with rationale
- **Configuration versioning**: Every decision linked to config SHA
- **Backtesting results**: Document and retain

### Broker ToS Compliance

- **Zerodha Kite Connect ToS**:
  - Respect rate limits (documented in API docs)
  - No credential sharing
  - Proper error handling and retries
  - Graceful degradation on API errors

## Production Deployment Checklist

Before deploying to production:

- [ ] All credentials in secure secrets management
- [ ] Database backups automated and tested
- [ ] HTTPS enabled with valid certificate
- [ ] Firewall rules configured
- [ ] Monitoring and alerting operational
- [ ] Kill switch tested and accessible
- [ ] Paper mode thoroughly tested
- [ ] Runbook reviewed and updated
- [ ] Incident response plan documented
- [ ] Team trained on system operations
- [ ] Compliance requirements verified
- [ ] Insurance reviewed (if applicable)

## Monitoring & Alerts

### Critical Alerts (Immediate Action)

- Daily loss limit breached
- Kill switch activated
- System error/crash
- API rate limit exceeded
- Unusual order rejection rate

### Warning Alerts (Review Required)

- Portfolio heat approaching limit
- Large slippage observed
- Strategy performance degradation
- High latency detected

### Monitoring Tools

- **Prometheus metrics**: `/metrics` endpoint
- **Structured logs**: JSON format in `logs/`
- **Telegram/Slack alerts**: Optional, configure in `app.yaml`

## Contact & Support

For security issues:
- **DO NOT** open public GitHub issues
- Email: [security contact - configure appropriately]
- PGP key: [if available]

---

**Remember: Capital preservation is the primary goal. When in doubt, PAUSE and review manually.**

