import pathlib
lines = pathlib.Path("app/services/market_brand_service.py").read_text("utf-8").splitlines()
print(f"Total lines: {len(lines)}")
for i, l in enumerate(lines):
    if l.strip().startswith("def ") or "═══" in l:
        print(f"  L{i+1:>4}: {l.strip()[:65]}")
