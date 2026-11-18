import json, os, urllib.request
BASE = os.getenv("FINGUARD_BASE_URL", "http://127.0.0.1:8001")
r = urllib.request.urlopen(f"{BASE}/health/ready", timeout=10)
assert r.status == 200 and json.loads(r.read())["status"] == "ready"
print("Compose smoke test passed!")
