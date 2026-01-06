"""
Announcements Router - NSE and BSE corporate announcements
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import Optional, List
import pandas as pd
import requests
import logging

from database import get_db
from routers.auth import get_current_user
from models import User

router = APIRouter()
logger = logging.getLogger(__name__)

# NSE API Headers
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
}

# BSE API Headers
BSE_HEADERS = {
    'authority': 'api.bseindia.com',
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'origin': 'https://www.bseindia.com',
    'referer': 'https://www.bseindia.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
}


def fetch_nse_announcements(
    symbol: str, 
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    limit: int = 100
) -> List[dict]:
    """Fetch corporate announcements from NSE API with optional date filtering"""
    url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={symbol}"
    
    try:
        with requests.Session() as s:
            s.headers.update(NSE_HEADERS)
            
            # Establish session
            s.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=10)
            
            # Fetch announcements
            response = s.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                return []
            
            # Transform data
            announcements = []
            for item in data:
                broadcast_date_str = item.get('an_dt', '')
                
                # Parse date for filtering (format: "02 Jan 2025")
                announcement_date = None
                if broadcast_date_str:
                    try:
                        announcement_date = datetime.strptime(broadcast_date_str.split()[0:3][0] + " " + 
                                                              broadcast_date_str.split()[1] + " " + 
                                                              broadcast_date_str.split()[2], '%d %b %Y').date()
                    except (ValueError, IndexError):
                        try:
                            # Try alternative format
                            announcement_date = datetime.strptime(broadcast_date_str[:11], '%d-%b-%Y').date()
                        except ValueError:
                            pass
                
                # Apply date filtering if dates are provided
                if from_date and announcement_date and announcement_date < from_date:
                    continue
                if to_date and announcement_date and announcement_date > to_date:
                    continue
                
                announcements.append({
                    "symbol": item.get('symbol', ''),
                    "company_name": item.get('sm_name', ''),
                    "subject": item.get('desc', ''),
                    "broadcast_date": broadcast_date_str,
                    "attachment_link": item.get('attchmntFile', ''),
                    "category": item.get('attchmntText', '')
                })
                
                # Apply limit
                if len(announcements) >= limit:
                    break
            
            return announcements
            
    except Exception as e:
        logger.error(f"Error fetching NSE announcements for {symbol}: {e}")
        return []


def fetch_bse_announcements(
    scrip_code: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    page: int = 1
) -> dict:
    """Fetch corporate announcements from BSE API"""
    
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        to_date = date.today()
    
    from_str = from_date.strftime("%Y%m%d")
    to_str = to_date.strftime("%Y%m%d")
    
    params = {
        'pageno': page,
        'strCat': -1,
        'strPrevDate': from_str,
        'strScrip': scrip_code or '',
        'strSearch': 'P',
        'strToDate': to_str,
        'strType': 'C'
    }
    
    query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
    url = f'https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?{query_string}'
    
    try:
        response = requests.get(url, headers=BSE_HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        announcements = []
        table_data = data.get('Table', [])
        
        # Threshold date for AttachLive vs AttachHis (like Streamlit line 150)
        threshold_date = date.today() - timedelta(days=2)
        
        for item in table_data:
            # Generate attachment URL based on date (matching Streamlit lines 153-159)
            attachment_name = item.get('ATTACHMENTNAME', '')
            attachment_url = None
            
            if attachment_name:
                news_date_str = item.get('News_submission_dt', '')
                try:
                    # Parse the date from the news_submission_dt field
                    # Format is typically "03-Jan-2025 15:30:45"
                    if news_date_str:
                        parsed_date = datetime.strptime(news_date_str.split()[0], '%d-%b-%Y').date()
                        if parsed_date >= threshold_date:
                            attachment_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment_name}"
                        else:
                            attachment_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{attachment_name}"
                    else:
                        # Default to AttachHis if date parsing fails
                        attachment_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{attachment_name}"
                except Exception:
                    # Default to AttachHis if date parsing fails
                    attachment_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{attachment_name}"
            
            announcements.append({
                "scrip_code": item.get('SCRIP_CD', ''),
                "company_name": item.get('SLONGNAME', ''),
                "subject": item.get('HEADLINE', ''),
                "news_date": item.get('News_submission_dt', ''),
                "category": item.get('CATEGORYNAME', ''),
                "attachment_url": attachment_url,
                "news_id": item.get('NEWSID', '')
            })
        
        total_pages = table_data[0].get('TotalPageCnt', 1) if table_data else 1
        
        return {
            "announcements": announcements,
            "total_pages": total_pages,
            "current_page": page
        }
        
    except Exception as e:
        logger.error(f"Error fetching BSE announcements: {e}")
        return {"announcements": [], "total_pages": 0, "current_page": page}


@router.get("/nse/{symbol}")
async def get_nse_announcements(
    symbol: str,
    from_date: Optional[str] = Query(None, description="From date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="To date (YYYY-MM-DD)"),
    limit: int = Query(100, le=200, description="Maximum number of announcements"),
    current_user: User = Depends(get_current_user)
):
    """
    Get NSE corporate announcements for a specific symbol.
    Optionally filter by date range.
    """
    parsed_from = None
    parsed_to = None
    
    if from_date:
        try:
            parsed_from = datetime.strptime(from_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format. Use YYYY-MM-DD")
    
    if to_date:
        try:
            parsed_to = datetime.strptime(to_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format. Use YYYY-MM-DD")
    
    announcements = fetch_nse_announcements(symbol.upper(), parsed_from, parsed_to, limit)
    
    if not announcements:
        return {
            "symbol": symbol.upper(),
            "from_date": from_date,
            "to_date": to_date,
            "count": 0,
            "announcements": [],
            "message": "No announcements found for this symbol and date range"
        }
    
    return {
        "symbol": symbol.upper(),
        "from_date": from_date,
        "to_date": to_date,
        "count": len(announcements),
        "announcements": announcements
    }


@router.get("/bse")
async def get_bse_announcements(
    scrip_code: Optional[str] = Query(None, description="BSE scrip code"),
    from_date: Optional[str] = Query(None, description="From date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="To date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Page number"),
    current_user: User = Depends(get_current_user)
):
    """
    Get BSE corporate announcements.
    Can filter by scrip code and date range.
    """
    parsed_from = None
    parsed_to = None
    
    if from_date:
        try:
            parsed_from = datetime.strptime(from_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format. Use YYYY-MM-DD")
    
    if to_date:
        try:
            parsed_to = datetime.strptime(to_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format. Use YYYY-MM-DD")
    
    result = fetch_bse_announcements(
        scrip_code=scrip_code,
        from_date=parsed_from,
        to_date=parsed_to,
        page=page
    )
    
    return {
        "scrip_code": scrip_code,
        "from_date": from_date,
        "to_date": to_date,
        **result
    }


@router.get("/bse/scrip-codes")
async def get_bse_scrip_codes(
    current_user: User = Depends(get_current_user)
):
    """
    Get list of BSE scrip codes from the stored CSV file.
    """
    import os
    
    # Try multiple possible locations for the CSV file
    possible_paths = [
        'bse_scrip_codes.csv',           # Current directory
        '../bse_scrip_codes.csv',         # Parent directory (project root)
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'bse_scrip_codes.csv')
    ]
    
    df = None
    for path in possible_paths:
        try:
            df = pd.read_csv(path)
            break
        except FileNotFoundError:
            continue
    
    if df is None:
        raise HTTPException(status_code=404, detail="BSE scrip codes file not found")
    
    try:
        return {
            "count": len(df),
            "scrip_codes": df.to_dict(orient='records')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading scrip codes: {str(e)}")
