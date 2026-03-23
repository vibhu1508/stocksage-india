import requests
from datetime import date, datetime, timedelta, time, timezone
import logging

# Set up logging
logger = logging.getLogger(__name__)

# IST Offset
IST = timezone(timedelta(hours=5, minutes=30))

# NSE Holiday API
NSE_HOLIDAYS_URL = "https://www.nseindia.com/api/holiday-master?type=trading"

# Hardcoded fallback list for 2026 (verified/provided by user)
FALLBACK_HOLIDAYS_2026 = {
    date(2026, 1, 15),   # Municipal Corporation Election
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 3),    # Holi
    date(2026, 3, 26),   # Shri Ram Navami
    date(2026, 3, 31),   # Shri Mahavir Jayanti
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 28),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 9, 14),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 10),  # Diwali-Balipratipada
    date(2026, 11, 24),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}

# Global cache
_cached_holidays = set()
_last_fetch_date = None

def fetch_nse_holidays():
    """Fetch trading holidays from NSE official API."""
    global _cached_holidays, _last_fetch_date
    
    current_date = datetime.now(IST).date()
    # Only fetch once per day
    if _last_fetch_date == current_date and _cached_holidays:
        return _cached_holidays

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/report-detail/fo-equity-derivatives-holiday-calendar",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive"
    }

    try:
        # NSE often requires a session to be established with the base URL first
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        
        response = session.get(NSE_HOLIDAYS_URL, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        trading_holidays = data.get('trading', [])
        new_holidays = set()
        
        for h in trading_holidays:
            try:
                # Format: "26-Jan-2026"
                d_str = h.get('tradingDate')
                if d_str:
                    d_obj = datetime.strptime(d_str, "%d-%b-%Y").date()
                    new_holidays.add(d_obj)
            except (ValueError, TypeError):
                continue
        
        if new_holidays:
            _cached_holidays = new_holidays
            _last_fetch_date = current_date
            logger.info(f"Successfully fetched {len(new_holidays)} holidays from NSE API.")
            return _cached_holidays
            
    except Exception as e:
        logger.error(f"Failed to fetch holidays from NSE: {e}. Using fallback list.")
        # Combine fallback with any previously cached data
        _cached_holidays.update(FALLBACK_HOLIDAYS_2026)
        return _cached_holidays

    return _cached_holidays or FALLBACK_HOLIDAYS_2026

def is_market_holiday(target_date: date) -> bool:
    """Check if a date is a weekend or an NSE holiday."""
    # Weekends (Saturday=5, Sunday=6)
    if target_date.weekday() >= 5:
        return True
    
    # Get dynamic holidays (cached)
    holidays = fetch_nse_holidays()
    if target_date in holidays:
        return True
        
    return False

def get_latest_market_date(current_dt: datetime = None) -> date:
    """
    Calculates the latest available NSE market date based on the current time.
    Standard rule: 
    - Bhavcopy is generally available after 7:30 PM (19:30) IST.
    """
    if current_dt is None:
        current_dt = datetime.now(IST)
    elif current_dt.tzinfo is None:
        current_dt = current_dt.replace(tzinfo=IST)
    else:
        current_dt = current_dt.astimezone(IST)

    current_date = current_dt.date()
    current_time = current_dt.time()

    # Cutoff time for today's bhavcopy (7:30 PM)
    cutoff_time = time(19, 30)

    # Determine starting point for look-back
    if current_time < cutoff_time:
        search_start = current_date - timedelta(days=1)
    else:
        search_start = current_date

    temp_date = search_start
    # Security limit: don't look back more than 15 days
    for _ in range(15):
        if not is_market_holiday(temp_date):
            return temp_date
        temp_date -= timedelta(days=1)

    return temp_date
