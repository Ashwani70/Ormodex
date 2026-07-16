"""Test all inventory-related API endpoints and report status."""
import asyncio
import time
import httpx

BASE = "http://localhost:8001/api"

ENDPOINTS = [
    ("GET", "/warehouses"),
    ("GET", "/products"),
    ("GET", "/stock-transactions"),
    ("GET", "/inventory/v2/godowns"),
    ("GET", "/inventory/v2/items"),
    ("GET", "/inventory/v2/transfers"),
    ("GET", "/inventory/v2/units"),
    ("GET", "/inventory/v2/batches"),
    ("GET", "/inventory/v2/serials"),
    ("GET", "/inventory/v2/reports/stock-summary"),
    ("GET", "/inventory/v2/reports/stock-aging"),
    ("GET", "/inventory/v2/reports/low-stock"),
    ("GET", "/inventory/v2/warehouses/dashboard"),
    ("GET", "/inventory/v2/warehouses/next-code"),
    ("GET", "/stock-log/entries"),
    ("GET", "/stock-log/summary"),
    ("GET", "/stock-log/filters"),
    ("GET", "/categories"),
    ("GET", "/manufacturing/dashboard"),
    ("GET", "/manufacturing/bom"),
    ("GET", "/manufacturing/boms"),  # verified plural alias works
    ("GET", "/manufacturing/work-orders"),
    ("GET", "/manufacturing/production-journals"),
    ("GET", "/job-work/challans"),
    ("GET", "/job-work/dashboard"),
    ("GET", "/job-work/receipts"),
]

async def main():
    async with httpx.AsyncClient(timeout=45.0) as client:
        # Login
        try:
            r = await client.post(f"{BASE}/auth/login", json={
                "email": "admin@ormodex.com",
                "password": "Admin@123456"
            })
        except Exception as e:
            print(f"LOGIN CONNECTION ERROR: {e}")
            return
            
        if r.status_code != 200:
            print(f"LOGIN FAILED: {r.status_code} {r.text[:200]}")
            return
        token = r.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        print(f"Login OK, token={token[:20]}...\n")

        results = []
        for method, path in ENDPOINTS:
            start = time.perf_counter()
            try:
                resp = await client.request(method, f"{BASE}{path}", headers=headers)
                elapsed = (time.perf_counter() - start) * 1000
                status = resp.status_code
                body = resp.text[:200] if status >= 400 else f"({len(resp.text)} bytes)"
                tag = "OK" if status < 400 else "ERR"
                print(f"{tag} {status:3d} {elapsed:7.0f}ms {method:4s} {path}")
                if status >= 400:
                    print(f"     Detail: {body}")
                results.append((path, status, elapsed))
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                print(f"EXC         {elapsed:7.0f}ms {method:4s} {path} -> {e}")
                results.append((path, 0, elapsed))

        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        ok = [r for r in results if 200 <= r[1] < 400]
        err = [r for r in results if r[1] >= 400 or r[1] == 0]
        print(f"  Total: {len(results)}, OK: {len(ok)}, Error: {len(err)}")
        if err:
            print("\n  FAILED ENDPOINTS:")
            for path, status, ms in err:
                print(f"    {status:3d} {path} ({ms:.0f}ms)")
        avg_ms = sum(r[2] for r in ok) / len(ok) if ok else 0
        print(f"\n  Average response time (OK endpoints): {avg_ms:.0f}ms")

asyncio.run(main())
