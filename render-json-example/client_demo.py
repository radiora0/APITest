import requests

BASE_URL = "https://render-json-example.onrender.com"

def main():
    payload = {
        "lot_no": "LOT-20260303-001",
        "line": "L1",
        "tire_model": "205/55R16",
        "quantity": 120,
        "qc_result": "PASS",
        "note": "Shift A",
    }

    # 보내기(POST)
    r = requests.post(f"{BASE_URL}/tire-productions", json=payload, timeout=20)
    r.raise_for_status()
    created = r.json()
    print("✅ SENT(JSON) -> saved in Postgres:")
    print(created)

    # 받기(GET)
    record_id = created["id"]
    r = requests.get(f"{BASE_URL}/tire-productions/{record_id}", timeout=20)
    r.raise_for_status()
    fetched = r.json()
    print("\n📥 RECEIVED(JSON) <- fetched from Postgres:")
    print(fetched)

if __name__ == "__main__":
    main()
