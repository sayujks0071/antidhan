import math
import logging

logger = logging.getLogger("OptionAnalytics")

def norm_cdf(x):
    """Cumulative distribution function for the standard normal distribution"""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def norm_pdf(x):
    """Probability density function for the standard normal distribution"""
    return (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x**2)

def calculate_greeks(S, K, T, r, sigma, option_type='ce'):
    """
    Calculate Greeks using Black-Scholes Model.
    S: Spot Price
    K: Strike Price
    T: Time to Expiry (in years)
    r: Risk-free rate (decimal, e.g., 0.05)
    sigma: Implied Volatility (decimal, e.g., 0.20)
    option_type: 'ce' for Call, 'pe' for Put
    """
    try:
        # Handle edge cases
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return {
                "delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0
            }

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type.lower() == 'ce' or option_type.lower() == 'call':
            delta = norm_cdf(d1)
            theta = (- (S * norm_pdf(d1) * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * norm_cdf(d2)) / 365.0
            rho = K * T * math.exp(-r * T) * norm_cdf(d2)
        else:
            delta = -norm_cdf(-d1)
            theta = (- (S * norm_pdf(d1) * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * norm_cdf(-d2)) / 365.0
            rho = -K * T * math.exp(-r * T) * norm_cdf(-d2)

        gamma = norm_pdf(d1) / (S * sigma * math.sqrt(T))
        vega = S * math.sqrt(T) * norm_pdf(d1) / 100.0 # Standard convention: change for 1% IV change

        return {
            "delta": round(delta, 4),
            "gamma": round(gamma, 6),
            "theta": round(theta, 4),
            "vega": round(vega, 4),
            "rho": round(rho, 4)
        }
    except Exception as e:
        logger.error(f"Error calculating greeks: {e}")
        return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0}

def calculate_iv(price, S, K, T, r, option_type='ce', tol=1e-5, max_iter=100):
    """
    Calculate Implied Volatility using Newton-Raphson method.
    """
    sigma = 0.5 # Initial guess
    for i in range(max_iter):
        greeks = calculate_greeks(S, K, T, r, sigma, option_type)

        # Calculate theoretical price using BS
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type.lower() == 'ce' or option_type.lower() == 'call':
            theo_price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
        else:
            theo_price = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)

        diff = theo_price - price

        if abs(diff) < tol:
            return round(sigma, 4)

        vega = greeks['vega'] * 100 # Adjust back from 1% unit
        if vega == 0:
            break

        sigma = sigma - diff / vega

    return 0.0 # Failed to converge

def calculate_max_pain(chain_data):
    """
    Calculate Max Pain Strike.
    chain_data: List of dicts with 'strike', 'ce_oi', 'pe_oi'
    """
    try:
        strikes = [item['strike'] for item in chain_data]
        strikes.sort()

        total_loss = []
        for strike in strikes:
            loss = 0
            for item in chain_data:
                k = item['strike']
                ce_oi = item.get('ce_oi', 0)
                pe_oi = item.get('pe_oi', 0)

                # If market expires at 'strike'
                # Call writers lose if strike > k
                if strike > k:
                    loss += (strike - k) * ce_oi

                # Put writers lose if strike < k
                if strike < k:
                    loss += (k - strike) * pe_oi
            total_loss.append(loss)

        min_loss_idx = total_loss.index(min(total_loss))
        return strikes[min_loss_idx]
    except Exception as e:
        logger.error(f"Error calculating max pain: {e}")
        return None

def calculate_pcr(chain_data):
    """
    Calculate Put-Call Ratio based on Open Interest.
    """
    try:
        total_ce_oi = 0
        total_pe_oi = 0

        for item in chain_data:
            # Handle flattened or nested structure
            if 'ce_oi' in item:
                total_ce_oi += item.get('ce_oi', 0)
                total_pe_oi += item.get('pe_oi', 0)
            else:
                total_ce_oi += item.get('ce', {}).get('oi', 0)
                total_pe_oi += item.get('pe', {}).get('oi', 0)

        if total_ce_oi == 0:
            return 0
        return round(total_pe_oi / total_ce_oi, 2)
    except Exception as e:
        logger.error(f"Error calculating PCR: {e}")
        return 0
