import os
import re
from datetime import datetime, date, timedelta, timezone
import requests
from playwright.sync_api import sync_playwright

EMAIL = os.environ.get("POSKO_EMAIL", "").strip()
PASSWORD = os.environ.get("POSKO_PASSWORD", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# ==========================================================
# 1. ROTASI OTOMATIS 3 REGU PIKET SPKT
# Patokan: 28 Oktober 2026 = AIPTU SUTARMAN
# ==========================================================
DAFTAR_REGU_SPKT = [
    "AIPTU SUTARMAN",
    "AIPTU DIDIK SUBAGYO",
    "AIPTU SUHANDOKO",
]
TANGGAL_PATOKAN = date(2026, 10, 28)

def ambil_petugas_piket_hari_ini():
    wib_sekarang = datetime.now(timezone(timedelta(hours=7))).date()
    selisih_hari = (wib_sekarang - TANGGAL_PATOKAN).days
    indeks_regu = selisih_hari % len(DAFTAR_REGU_SPKT)
    return DAFTAR_REGU_SPKT[indeks_regu], indeks_regu + 1

# ==========================================================
# 2. LINK FOLDER GOOGLE DRIVE SPKT (QW4.1 s/d QW4.4)
# Silakan ganti link di bawah dengan link folder Google Drive Anda
# ==========================================================
FOLDER_URLS = {
    "qw4_1": "https://drive.google.com/drive/folders/GANTI_DENGAN_LINK_FOLDER_SPKT_QW4_1",
    "qw4_2": "https://drive.google.com/drive/folders/GANTI_DENGAN_LINK_FOLDER_SPKT_QW4_2",
    "qw4_3": "https://drive.google.com/drive/folders/GANTI_DENGAN_LINK_FOLDER_SPKT_QW4_3",
    "qw4_4": "https://drive.google.com/drive/folders/GANTI_DENGAN_LINK_FOLDER_SPKT_QW4_4",
}

DAFTAR_KEGIATAN_SPKT = [
    {
        "kode": "QW4.1",
        "key_folder": "qw4_1",
        "nama": "Pamapta hadir dan penanganan ke TKP"
    },
    {
        "kode": "QW4.2",
        "key_folder": "qw4_2",
        "nama": "Petugas Yanmas menerima laporan dan aduan di SPKT"
    },
    {
        "kode": "QW4.3",
        "key_folder": "qw4_3",
        "nama": "Respons cepat panggilan 110"
    },
    {
        "kode": "QW4.4",
        "key_folder": "qw4_4",
        "nama": "Layanan ramah perempuan dan anak"
    },
]

def kirim_notif_telegram(pesan, foto_path=None):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        if foto_path and os.path.exists(foto_path):
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            with open(foto_path, "rb") as f:
                requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": pesan[:1000]}, files={"photo": f}, timeout=20)
        else:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": TG_CHAT_ID, "text": pesan[:4000]}, timeout=20)
    except Exception as e:
        print("Gagal kirim ke Telegram:", e)

def ambil_satu_foto_dari_folder(page, kategori):
    """Membuka folder Google Drive dan memilih 1 link foto sesuai siklus hari."""
    folder_url = FOLDER_URLS[kategori]
    folder_id = folder_url.rstrip("/").split("/")[-1].split("?")[0]
    embed_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"

    wib_now = datetime.now(timezone(timedelta(hours=7))).date()
    selisih_hari = (wib_now - TANGGAL_PATOKAN).days

    file_links = []
    try:
        res = requests.get(embed_url, timeout=20)
        ids = re.findall(r"/file/d/([a-zA-Z0-9_-]{25,})/", res.text)
        if not ids:
            ids = re.findall(r'id="entry-([a-zA-Z0-9_-]{25,})"', res.text)
        
        seen = set()
        for fid in ids:
            if fid != folder_id and fid not in seen:
                seen.add(fid)
                file_links.append(f"https://drive.google.com/file/d/{fid}/view?usp=drivesdk")

        if not file_links:
            page.goto(folder_url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            html = page.content()
            ids2 = re.findall(r'data-id="([a-zA-Z0-9_-]{25,})"', html)
            for fid in ids2:
                if fid != folder_id and fid not in seen:
                    seen.add(fid)
                    file_links.append(f"https://drive.google.com/file/d/{fid}/view?usp=drivesdk")
    except Exception as e:
        print(f"Gagal memindai folder {kategori}:", e)

    if file_links:
        idx_terpilih = selisih_hari % len(file_links)
        return file_links[idx_terpilih], idx_terpilih + 1, len(file_links)

    return folder_url, 1, 1

def jalankan_robot_spkt():
    nama_petugas, nomor_regu = ambil_petugas_piket_hari_ini()
    kirim_notif_telegram(
        f"🤖 Robot SPKT Polsek Jatisrono mulai berjalan...\n"
        f"👮 Piket Hari Ini (Regu {nomor_regu}): {nama_petugas}"
    )
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 412, "height": 915},
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        )
        page = context.new_page()

        try:
            # 1. Ambil link foto untuk masing-masing kegiatan SPKT
            links_spkt = {}
            for item in DAFTAR_KEGIATAN_SPKT:
                k = item["key_folder"]
                links_spkt[k] = ambil_satu_foto_dari_folder(page, k)

            # 2. Buka halaman Posko PBM
            page.goto("https://poskopbm.polri.go.id/input", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # 3. Login jika diminta
            if page.locator("input[type='password']").count() > 0:
                page.locator("input[type='email'], input[type='text']").first.fill(EMAIL)
                page.locator("input[type='password']").first.fill(PASSWORD)
                page.get_by_role("button", name="Masuk").click()
                page.wait_for_timeout(5000)

            # 4. Isi Nama Pelapor sesuai Regu Piket & Pilih Jabatan "Ka SPKT (6 kegiatan)"
            page.get_by_label("Nama dan pangkat pelapor").fill(nama_petugas)
            page.locator("select").first.select_option(label="Ka SPKT (6 kegiatan)")
            page.wait_for_timeout(2000)

            # Pastikan tab QW4 terpilih
            tombol_qw4 = page.locator("button, div").filter(has_text="QW4 110 Respons Cepat")
            if tombol_qw4.count() > 0:
                tombol_qw4.last.click()
                page.wait_for_timeout(1500)

            # 5. Looping isi dan kirim keempat laporan SPKT (QW4.1 s/d QW4.4)
            for item in DAFTAR_KEGIATAN_SPKT:
                kode = item["kode"]
                nama_giat = item["nama"]
                link_foto, no_foto, tot_foto = links_spkt[item["key_folder"]]

                # Klik tombol kegiatan (QW4.1 / QW4.2 / QW4.3 / QW4.4)
                page.locator("button, div").filter(has_text=kode).filter(has_text=nama_giat).last.click()
                page.wait_for_timeout(2000)

                # Isi b. Nama dan pangkat pejabat pelaksana sesuai Regu Piket
                page.get_by_label("Nama dan pangkat pejabat pelaksana").fill(nama_petugas)

                # Khusus QW4.4: pastikan tombol "Ada" terpilih
                if kode == "QW4.4":
                    tombol_ada = page.get_by_role("button", name="Ada", exact=True)
                    if tombol_ada.count() > 0:
                        tombol_ada.first.click()

                # Isi Dokumentasi kegiatan (Link Google Drive)
                page.locator("input[placeholder*='drive.google.com']").fill(link_foto)
                page.wait_for_timeout(1000)

                # Klik Kirim laporan
                page.get_by_role("button", name="Kirim laporan").click()
                page.wait_for_timeout(4000)

                ss_path = f"bukti_{kode.replace('.', '_')}.png"
                page.screenshot(path=ss_path)
                kirim_notif_telegram(
                    f"✅ Laporan SPKT {kode} berhasil dikirim!\n\n"
                    f"📌 Kegiatan: {nama_giat}\n"
                    f"👮 Pelapor & Pelaksana: {nama_petugas} (Regu {nomor_regu})\n"
                    f"📸 Foto ke-{no_foto} dari {tot_foto} di Folder\n"
                    f"🔗 Link: {link_foto}",
                    ss_path
                )

        except Exception as e:
            err_ss = "error_spkt.png"
            try:
                page.screenshot(path=err_ss)
                kirim_notif_telegram(f"⚠️ Gagal mengirim laporan SPKT ({nama_petugas}):\n{str(e)}", err_ss)
            except Exception:
                kirim_notif_telegram(f"⚠️ Gagal membuka web SPKT ({nama_petugas}):\n{str(e)}")
        finally:
            browser.close()

if __name__ == "__main__":
    jalankan_robot_spkt()
