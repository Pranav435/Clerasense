"""Quick test: fetch Indian Medicine Dataset and search for paracetamol brands."""
import requests, json, time, sys

URL = "https://raw.githubusercontent.com/junioralive/Indian-Medicine-Dataset/main/DATA/indian_medicine_data.json"

print("Fetching dataset...")
t0 = time.time()
resp = requests.get(URL, timeout=120)
t1 = time.time()
print(f"Status: {resp.status_code}, Size: {len(resp.content)} bytes, Time: {t1-t0:.1f}s")

if resp.status_code != 200:
    print("FAILED"); sys.exit(1)

data = resp.json()
print(f"Records: {len(data)}")
print(f"Sample: {json.dumps(data[0], indent=2)}")

# Search for paracetamol
drug = "paracetamol"
matches = [m for m in data if drug.lower() in (m.get("short_composition1","") or "").lower()]
print(f"\nMatches for '{drug}': {len(matches)}")
for m in matches[:10]:
    print(f"  {m['name']} | {m['manufacturer_name']} | Rs.{m.get('price(₹)','')} | {m.get('pack_size_label','')} | {m.get('short_composition1','')}")

# Search for metformin
drug2 = "metformin"
matches2 = [m for m in data if drug2.lower() in (m.get("short_composition1","") or "").lower()]
print(f"\nMatches for '{drug2}': {len(matches2)}")
for m in matches2[:10]:
    print(f"  {m['name']} | {m['manufacturer_name']} | Rs.{m.get('price(₹)','')} | {m.get('pack_size_label','')} | {m.get('short_composition1','')}")
