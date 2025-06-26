import requests
import json
from datetime import datetime

common_headers = {"Accept": "application/json, text/plain, */*",
                  "Accept-Encoding": "gzip, deflate, br, zstd",
                  "Accept-Language": "tr-TR",
                  "Access-Control-Allow-Credentials": "true",
                  "Access-Control-Allow-Headers": "Authorization,Content-Type, Accept, X-Requested-With, remember-me",
                  "Access-Control-Allow-Methods": "DELETE, POST, GET, OPTIONS",
                  "Access-Control-Allow-Origin": "*",
                  "Access-Control-Max-Age": "3600",
                  "Connection": "keep-alive",
                  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"})


def check_active(authorization):
    menu_url = "https://prd.mhrs.gov.tr/api/vatandas/menu"
    headers = common_headers.copy()
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = authorization
    response = session.get(menu_url, headers=headers)
    response_data = json.loads(response.content)
    if response_data["success"]:
        return True
    return False


def login(username, password):
    login_url = "https://prd.mhrs.gov.tr/api/vatandas/login"
    headers = common_headers.copy()
    headers["Content-Type"] = "application/json"
    data = {"kullaniciAdi": username,
            "parola": password,
            "islemKanali": "VATANDAS_RESPONSIVE",
            "girisTipi": "PAROLA",
            "captchaKey": None}
    response = session.post(login_url, json=data, headers=headers)
    response_data = json.loads(response.content)
    if response_data["success"]:
        authorization = f"Bearer {response_data['data']['jwt']}"
        print("Giriş Başarılı.")
        return authorization
    print("Giriş Başarısız! TC Kimlik Numaranızı ve Şifrenizi Kontrol Ediniz.")
    print(response_data)
    return None


def logout(authorization):
    logout_url = "https://prd.mhrs.gov.tr/api/vatandas/logout"
    headers = common_headers.copy()
    headers["Authorization"] = authorization
    response = session.post(logout_url, headers=headers)
    response_data = json.loads(response.content)
    if response_data["success"]:
        print("Çıkış Yapıldı.")
        headers.pop("Authorization")
        return True
    print("Çıkış Başarısız!")
    return False


def extract_items(items):
    text_value = []
    for item in items:
        text = item["text"]
        value = item["value"]
        text_value.append([text, value])
        if "children" in item:
            for subitem in item["children"]:
                text = subitem["text"]
                value = subitem["value"]
                text_value.append([text, value])
    return text_value


def get(key, authorization, *values):
    urls = {"city": "https://prd.mhrs.gov.tr/api/yonetim/genel/il/selectinput-tree",
            "district": lambda v1: f"https://prd.mhrs.gov.tr/api/yonetim/genel/ilce/selectinput/{v1}",
            "clinic": lambda v1, v2: f"https://prd.mhrs.gov.tr/api/kurum/kurum/kurum-klinik/il/{v1}/ilce/{v2}/kurum/-1/aksiyon/200/select-input",
            "hospital": lambda v1, v2, v3: f"https://prd.mhrs.gov.tr/api/kurum/kurum/kurum-klinik/il/{v1}/ilce/{v2}/kurum/-1/klinik/{v3}/ana-kurum/select-input",
            "examination": lambda v1, v2: f"https://prd.mhrs.gov.tr/api/kurum/kurum/muayene-yeri/ana-kurum/{v1}/kurum/-1/klinik/{v2}/select-input",
            "doctor": lambda v1, v2: f"https://prd.mhrs.gov.tr/api/kurum/hekim/hekim-klinik/hekim-select-input/anakurum/{v1}/kurum/-1/klinik/{v2}"}
    try:
        url = urls[key](*values)
    except TypeError:
        url = urls[key]
    headers = common_headers.copy()
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = authorization
    response = session.get(url, headers=headers)
    response_data = json.loads(response.content)
    items = extract_items(response_data if key == 'city' or key == 'district' else response_data["data"])

    return items


def get_appointments(city, district, clinic, hospital, examination, doctor, start_date, end_date, authorization):
    appointment_url = "https://prd.mhrs.gov.tr/api/kurum-rss/randevu/slot-sorgulama/arama"
    headers = common_headers.copy()
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = authorization
    data = {"aksiyonId": "200",
            "cinsiyet": "F",
            "mhrsHekimId": doctor,
            "mhrsIlId": city,
            "mhrsIlceId": district,
            "mhrsKlinikId": clinic,
            "mhrsKurumId": hospital,
            "muayeneYeriId": examination,
            "tumRandevular": False,
            "ekRandevu": True,
            "randevuZamaniList": [],
            }
    if start_date:
        today = datetime.now()
        data["baslangicZamani"] = f"{start_date} {today.strftime('%H:%M:%S')}"
        if end_date:
            data["bitisZamani"] = f"{end_date} {today.strftime('%H:%M:%S')}"

    too_many_requests = False
    appointments = []
    response = session.post(appointment_url, json=data, headers=headers)
    if response.status_code == 200 or response.status_code == 428:
        response_data = json.loads(response.content)
        if response_data["data"]:
            appointments = response_data["data"]["hastane"] + response_data["data"]["semt"]
        else:
            print(response_data)
            too_many_requests = True
    elif response.status_code == 404:
        print("Aradığınız kriterlerde uygun randevu bulunamadı. Kriterleri değiştirip tekrar arama yapabilirsiniz.")
    else:
        print(f"Bir hata meydana geldi!\nStatus Code: {response.status_code}\nResponse: {response.content}")
    return appointments, too_many_requests


def get_appointment_hours(city, clinic, hospital, examination, doctor, authorization):
    hour_url = "https://prd.mhrs.gov.tr/api/kurum-rss/randevu/slot-sorgulama/slot"
    headers = common_headers.copy()
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = authorization
    data = {"aksiyonId": "200",
            "cinsiyet": "F",
            "mhrsHekimId": doctor,
            "mhrsIlId": city,
            "mhrsKlinikId": clinic,
            "mhrsKurumId": hospital,
            "muayeneYeriId": examination,
            "tumRandevular": False,
            "ekRandevu": True,
            "randevuZamaniList": []
            }
    response = session.post(hour_url, json=data, headers=headers)
    all_hours = []
    if response.status_code == 200:
        response_data = json.loads(response.content)
        for day in response_data["data"]:
            for slot in day["hekimSlotList"][0]["muayeneYeriSlotList"][0]["saatSlotList"]:
                for hour in slot["slotList"]:
                    if hour["bos"]:
                        all_hours.append([day["gunStr"]["tarih"], [hour["id"], hour["baslangicZamanStr"]["saat"]]])

    return all_hours


def make_appointment(slot_id, authorization):
    appointment_info_url = f"https://prd.mhrs.gov.tr/api/kurum/randevu/slot-sorgulama/randevu-bilgileri?fkSlotId={slot_id}"
    make_appointment_url = "https://prd.mhrs.gov.tr/api/kurum/randevu/randevu-ekle"
    headers = common_headers.copy()
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = authorization
    response = session.get(appointment_info_url, headers=headers)
    if response.status_code == 200:
        response_data = json.loads(response.content)["data"]
        data = {"baslangicZamani": response_data["randevuBaslangicZamani"],
                "bitisZamani": response_data["randevuBitisZamani"],
                "fkCetvelId": response_data["slot"]["fkCetvelId"],
                "fkSlotId": response_data["slot"]["id"],
                "muayeneYeriId": response_data["slot"]["muayeneYeriId"],
                "randevuNotu": "",
                "yenidogan": False}
    else:
        print("Randevu alınırken bir hata meydana geldi. Response:", response.content)
        return False

    response = session.post(make_appointment_url, json=data, headers=headers)
    if response.status_code == 200:
        print(json.loads(response.content)["infos"][0]["mesaj"])
        return True
    else:
        print("Randevu alınırken bir hata meydana geldi. Response:", response.content)
        return False


def get_active_appointments(authorization):
    active_appointments_url = "https://prd.mhrs.gov.tr/api/kurum/randevu/yaklasan-randevularim"
    headers = common_headers.copy()
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = authorization
    response = session.get(active_appointments_url, headers=headers)
    active_appointments = []
    if response.status_code == 200:
        response_data = json.loads(response.content)["data"]
        active_appointments = response_data["aktifRandevuDtoList"]
    return active_appointments


def cancel_appointment(appointment_no, authorization):
    cancel_appointment_url = f"https://prd.mhrs.gov.tr/api/kurum/randevu/iptal-et/{appointment_no}"
    headers = common_headers.copy()
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = authorization
    response = requests.get(cancel_appointment_url, headers=headers)
    print(response.content)
    if response.status_code == 200:
        print("Randevu iptali başarılı. 5 dakika sonra randevu kalıcı olarak sistemden silinecektir.")
        return True
    else:
        print("Randevu iptali başarısız.")
        return False


def get_personal_data(authorization):
    url = "https://prd.mhrs.gov.tr/api/vatandas/kimlik-bilgileri"
    headers = common_headers.copy()
    headers["Authorization"] = authorization
    response = session.get(url, headers=headers)
    response_data = json.loads(response.content)
    if response_data["success"]:
        personal_data = {"tc_id": response_data["data"]["tcKimlikNo"], "name": response_data["data"]["ad"],
                         "surname": response_data["data"]["soyad"], "birthdate": response_data["data"]["dogumTarihi"],
                         "gender": response_data["data"]["cinsiyet"]["valText"]}
    else:
        personal_data = None

    return personal_data
