import requests

BASE_URL = "https://apptest-96et.onrender.com"  # 배포 후 바꾸기

def main():
    # 1) JSON POST로 "택배 접수" (서버에 데이터 보내기)
    payload = {
        "sender": "홍길동",
        "receiver": "김철수",
        "address": "서울특별시 강남구 어딘가 123",
        "item": "노트북",
        "note": "문 앞에 두세요",
    }

    r = requests.post(f"{BASE_URL}/shipments", json=payload, timeout=15)
    r.raise_for_status()
    created = r.json()
    print("✅ Created shipment:")
    print(created)

    shipment_id = created["id"]

    # 2) JSON GET으로 조회 (서버에서 데이터 받기)
    r = requests.get(f"{BASE_URL}/shipments/{shipment_id}", timeout=15)
    r.raise_for_status()
    fetched = r.json()
    print("\n📦 Fetched shipment:")
    print(fetched)

if __name__ == "__main__":
    main()
