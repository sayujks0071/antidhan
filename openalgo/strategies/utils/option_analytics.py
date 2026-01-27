"""
Option Analytics Module
Implements Black-Scholes Greeks and IV calculations using standard math library.
"""
import math

def norm_pdf(x):
    """Standard normal probability density function"""
    return (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x)

def norm_cdf(x):
    """Standard normal cumulative distribution function"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def d1_d2(S, K, T, r, sigma):
    """Calculate d1 and d2 parameters"""
    if T <= 0 or sigma <= 0:
        return 0, 0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2

def calculate_greeks(S, K, T, r, sigma, option_type='ce'):
    """
    Calculate Greeks for an option.
    S: Spot Price
    K: Strike Price
    T: Time to Expiry (in years)
    r: Risk-free rate (decimal, e.g., 0.05)
    sigma: Volatility (decimal, e.g., 0.20)
    option_type: 'ce' or 'pe'
    """
    if T <= 0:
        return {'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0, 'rho': 0, 'price': 0}

    d1, d2 = d1_d2(S, K, T, r, sigma)

    # Common terms
    pdf_d1 = norm_pdf(d1)
    cdf_d1 = norm_cdf(d1)
    cdf_d2 = norm_cdf(d2)
    cdf_neg_d1 = norm_cdf(-d1)
    cdf_neg_d2 = norm_cdf(-d2)

    sqrt_T = math.sqrt(T)

    # Gamma (Same for Call and Put)
    gamma = pdf_d1 / (S * sigma * sqrt_T)

    # Vega (Same for Call and Put, usually shown /100 for 1% change)
    vega = S * pdf_d1 * sqrt_T / 100.0

    if option_type.lower() == 'ce':
        price = S * cdf_d1 - K * math.exp(-r * T) * cdf_d2
        delta = cdf_d1
        theta = (- (S * pdf_d1 * sigma) / (2 * sqrt_T)
                 - r * K * math.exp(-r * T) * cdf_d2) / 365.0
        rho = (K * T * math.exp(-r * T) * cdf_d2) / 100.0
    else:
        price = K * math.exp(-r * T) * cdf_neg_d2 - S * cdf_neg_d1
        delta = cdf_d1 - 1
        theta = (- (S * pdf_d1 * sigma) / (2 * sqrt_T)
                 + r * K * math.exp(-r * T) * cdf_neg_d2) / 365.0
        rho = (-K * T * math.exp(-r * T) * cdf_neg_d2) / 100.0

    return {
        'price': price,
        'delta': delta,
        'gamma': gamma,
        'theta': theta,
        'vega': vega,
        'rho': rho
    }

def implied_volatility(price, S, K, T, r, option_type='ce'):
    """
    Calculate Implied Volatility using Newton-Raphson method.
    """
    sigma = 0.5 # Initial guess
    tol = 1e-5
    max_iter = 100

    for i in range(max_iter):
        greeks = calculate_greeks(S, K, T, r, sigma, option_type)
        diff = greeks['price'] - price

        if abs(diff) < tol:
            return sigma

        vega = greeks['vega'] * 100 # Back to raw vega for calculation

        if vega == 0:
            break

        sigma = sigma - diff / vega

    return sigma
