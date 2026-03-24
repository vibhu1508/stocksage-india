import math
from scipy.stats import norm

def black_scholes(S, K, T, r, sigma, option_type='CE'):
    """
    Calculate Option Price and Greeks using Black-Scholes model
    S: Current Price
    K: Strike Price
    T: Time to expiry (in years)
    r: Risk-free rate (e.g. 0.07 for 7%)
    sigma: Volatility (standard deviation of the stock's returns)
    """
    if T <= 0:
        if option_type == 'CE':
            price = max(0, S - K)
            delta = 1.0 if S > K else 0.0
        else:
            price = max(0, K - S)
            delta = -1.0 if K > S else 0.0
        return {"price": price, "delta": delta, "gamma": 0, "theta": 0, "vega": 0}

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == 'CE':
        price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (- (S * sigma * norm.pdf(d1)) / (2 * math.sqrt(T)) 
                 - r * K * math.exp(-r * T) * norm.cdf(d2))
    else:
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
        theta = (- (S * sigma * norm.pdf(d1)) / (2 * math.sqrt(T)) 
                 + r * K * math.exp(-r * T) * norm.cdf(-d2))

    gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * math.sqrt(T) * norm.pdf(d1) / 100 # per 1% change in sigma
    
    # Yearly theta to Daily theta
    theta = theta / 365

    return {
        "price": price,
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega
    }
