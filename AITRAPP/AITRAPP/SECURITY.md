SECURITY.md# Security Policy

## SEBI Retail Algo Participation Guardrails

**Reference:** SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013  
**Date:** February 4, 2025

This trading system complies with SEBI's regulatory framework for retail algorithmic trading participation. The following security guardrails are enforced:

### 1. Authentication & Authorization

- **OAuth-Only Access:** All API access uses OAuth 2.0 with broker-issued tokens. No passwords are stored.
- **2FA Enforcement:** Two-factor authentication is required at the broker level (Zerodha Kite).
- **No Open APIs:** All endpoints require authentication; no public/open API access is permitted.
- **Static IP Allowlisting:** API keys are restricted to pre-registered static IPs as configured with the broker.

### 2. Broker-as-Principal Model

- All trades are executed through registered broker (Zerodha) with proper risk management controls.
- The system operates under broker supervision with broker-side risk limits enforced.
- Broker maintains first-level risk controls including position limits and margin requirements.

### 3. Order Tagging & Traceability

- **Unique Client Order IDs:** Every order includes a unique `client_order_id` for full audit trail.
- **Algo Identification:** All orders are tagged with algo identifiers as per SEBI requirements.
- **Trade Logging:** Complete audit log of all trading decisions, orders, and executions.

### 4. Kill Switch & Risk Controls

- **Manual Kill Switch:** `/flatten` endpoint immediately closes all positions and pauses trading.
- **Rate Limiting:** Order placement is throttled to prevent runaway algo behavior.
- **Daily Loss Caps:** Maximum daily loss limits enforced (configurable per config).
- **Portfolio Heat Limits:** Maximum portfolio exposure capped at configured levels.
- **Position Size Limits:** Per-symbol and total position limits enforced.

### 5. Mode Controls

- **PAPER Mode Default:** System defaults to simulation/paper trading mode.
- **Manual LIVE Switch:** Transition to LIVE mode requires explicit human operator action.
- **No Automated LIVE Switch:** CI/CD pipelines cannot automatically enable LIVE trading.
- **Day-2 Burn-in Required:** LIVE mode switch requires passing Day-2 burn-in validation (see workflows).

### 6. Audit Logging

- All trading actions logged with:
  - Action type (enum)
  - Timestamp (ISO 8601 with timezone)
  - User/system identifier
  - Details (JSONB structure)
  - Outcome/result
- Logs are immutable and retained as per regulatory requirements.
- Database-level audit trail using PostgreSQL `audit_log` table.

### 7. Scheduled Workflows & Validation

- **Automated PAPER Sessions:** Scheduled GitHub Actions workflows run preopen checks and postclose reports.
- **No Scheduled LIVE:** LIVE mode is never triggered by scheduled jobs.
- **Day-2 Validation:** Manual LIVE gate workflow validates burn-in requirements before permitting switch.
- **Artifacts Retention:** All workflow artifacts (reports, logs, metrics) retained for audit.

### 8. Compliance Monitoring

- `/compliance/status` endpoint provides real-time compliance posture.
- Pre-live gates check all safety requirements before allowing LIVE switch.
- Daily logout enforcement (SEBI/NSE requirement) implemented via cron.
- Egress IP verification to detect network configuration changes.

---

## Reporting Security Issues

If you discover a security vulnerability in this system, please report it via:

- Email: [YOUR_EMAIL]
- GitHub Security Advisories (private disclosure)

**Do NOT open public issues for security vulnerabilities.**

---

## Security Best Practices for Operators

1. **Never share API keys or secrets**
2. **Use environment variables, never hard-code credentials**
3. **Rotate API tokens regularly**
4. **Monitor compliance status daily**
5. **Review audit logs for anomalies**
6. **Test kill switch functionality weekly**
7. **Validate burn-in requirements before LIVE switch**
8. **Keep runner machines secure and up-to-date**

---

## References

- [SEBI Circular on Algo Trading](https://www.sebi.gov.in/legal/circulars/)
- [NSE Algo Trading Guidelines](https://www.nseindia.com/)
- [Zerodha Kite Connect API Documentation](https://kite.trade/docs/connect/v3/)
