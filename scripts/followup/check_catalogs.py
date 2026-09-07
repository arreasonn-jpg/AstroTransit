import requests
import json

targets = [52005579, 150428135, 352179145, 439949948, 303241161]

print("="*60)
print("5 HEDEFN NASA EXOPLANET ARCHIVE KATALOG KONTROLÜ")
print("="*60)

for tid in targets:
    url = f"https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+toi,tfopwg_disp,pl_orbper,pl_rade+from+toi+where+tid={tid}&format=json"
    r = requests.get(url)
    if r.status_code == 200 and len(r.json()) > 0:
        data = r.json()[0]
        print(f"TIC {tid:<10} -> NASA TOI Bulundu: TOI-{data.get('toi')} | Statü: {data.get('tfopwg_disp')} | Rp: {data.get('pl_rade')} R_e")
    else:
        print(f"TIC {tid:<10} -> NASA TOI Listesinde Yok (ÖZGÜN / ADAY GEZEGEN)")
print("="*60)
