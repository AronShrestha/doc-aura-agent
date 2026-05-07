import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import pandas
import threading

headers = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "priority": "u=1, i",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest",
    "cookie": "ASP.NET_SessionId=ktyzuodwdumjk4fnkt5sfugt",
    "Referer": "https://merolagani.com/LatestMarket.aspx",
}

data = {
    "value": "",
    "sector": "0",
}

# Fetch company list
print("Fetching company list...")
response = requests.post(
    "https://merolagani.com/handlers/AutoSuggestHandler.ashx?type=Company",
    headers=headers,
    data=data,
    timeout=10,
)

data = response.json()
company_df = pandas.DataFrame(data)

# company_df.to_csv("companies.csv", index=False)

print(f"Total companies: {len(company_df['d'])}")

# Thread-safe list for storing results
company_details = []
lock = threading.Lock()

def scrape_company(code, index):
    """Scrape details for a single company"""
    try:
        r = requests.get(
            f"https://merolagani.com/CompanyDetail.aspx?symbol={code}",
            timeout=10,
        )
        
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", {"id": "accordion"})
        
        if not table:
            print(f"  [{index}] {code}: No table found")
            return None
        
        company_detail = {"code": code}
        
        for row in table.find_all("tr"):
            header = row.find("th")
            if not header:
                continue
            
            header = header.text.strip()
            
            if value := row.find("td"):
                value = value.text.strip()
            
            if not value:
                continue
            
            try:
                value = float(value)
            except ValueError:
                pass
            
            company_detail[header] = value
        
        print(f"  [{index}] {code}: Success")
        return company_detail
        
    except Exception as e:
        print(f"  [{index}] {code}: Error - {str(e)}")
        return None

# Use ThreadPoolExecutor with 8 threads
total_companies = len(company_df["d"])
print("Scraping company details with 20 threads...")
completed = 0

with ThreadPoolExecutor(max_workers=20) as executor:
    # Submit all tasks
    future_to_company = {
        executor.submit(scrape_company, company, i): (company, i) 
        for i, company in enumerate(company_df["d"])
    }
    
    # Collect results as they complete
    for future in as_completed(future_to_company):
        result = future.result()
        if result:
            with lock:
                company_details.append(result)
        completed += 1
        if completed % 10 == 0 or completed == total_companies:
            print(f"Progress: {completed}/{total_companies} companies processed ({completed/total_companies*100:.1f}%)")


company_df = pandas.DataFrame(company_details)

company_df.to_csv("company_details.csv", index=False)

company_df = company_df[company_df["Shares Outstanding"].notna()]

company_df.to_csv("valid_company_details.csv", index=False)
