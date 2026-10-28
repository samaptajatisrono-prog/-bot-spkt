import os
import re
from datetime import datetime, date, timedelta, timezone
import requests
from playwright.sync_api import sync_playwright

EMAIL = os.environ.get("POSKO_EMAIL", "").strip()
PASSWORD = os.environ.get("POSKO_PASSWORD", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DEFAULT_LINK = "https://drive.google.com/file/d/17KmVFmPU-OZk0dBdbVgF7AZ6ayhGWPyl/view?usp=drivesdk"

# ==========================================================
# 1. KONFIGURASI 3 REGU PIKET SPKT & LINK FOLDER (40 FOTO)
# Patokan mulai: 28 Oktober 2026 = Regu 1 (AIPTU SUTARMAN)
# ==========================================================
TANGGAL_PATOKAN = date(2026, 10, 28)

DAFTAR_REGU_SPKT = [
    {
        "regu": 1,
        "nama": "AIPTU SUTARMAN",
        "folder_url": "https://drive.google.com/drive/folders/1aNKfkXJ7TBBQNvJNUcRcNshy_oLeT8jf"
    },
    {
        "regu": 2,
        "nama": "AIPTU DIDIK SUBAGYO",
        "folder_url": "https://drive.google.com/drive/folders/1HrneM25AB_t1YctvCWEiRq-ap2sKvL9j"
    },
    {
        "regu": 3,
        "nama": "AIPTU SUHANDOKO",
        "folder_url": "https://drive.google.com/drive/folders/11fsqOzZFotnDS5vkPf8rQR1f9qQ_ukA5"
    },
]

# 4 Kegiatan Harian SPKT (Memakai 4 Foto Berbeda Tiap Hari)
DAFTAR_KEGIATAN_SPKT = [
    {"kode": "QW4.1", "nama": "Pamapta hadir dan penanganan ke TKP"},
    {"kode": "QW4.2", "nama": "Petugas Yanmas menerima laporan dan aduan di SPKT"},
    {"kode": "QW4.3", "nama": "Respons cepat panggilan 110"},
    {"kode": "QW4.4", "nama": "Layanan ramah perempuan dan anak"},
]

def hitung_jadwal_regu_hari_ini():
    """Menentukan regu yang piket hari ini dan urutan piket ke-berapa bagi regu tersebut."""
    wib_sekarang = datetime.now(timezone(timedelta(hours=7))).date()
    selisih_hari = max(0, (wib_sekarang - TANGGAL_PATOKAN).days)
    
    indeks_regu = selisih_hari % len(DAFTAR_REGU_SPKT)
    putaran_piket_regu = selisih_hari // len(DAFTAR_REGU_SPKT)  # Piket ke-0, 1, 2, dst.
    
    return DAFTAR_REGU_SPKT[indeks_regu], putaran_piket_regu

def kirim_notif_telegram(pesan, foto_path=None):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    daftar_chat_id = [cid.strip() for cid in TG_CHAT_ID.split(",") if cid.strip()]
    for cid in daftar_chat_id:
        try:
            if foto_path and os.path.exists(foto_path):
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                with open(foto_path, "rb") as f:
                    requests.post(url, data={"chat_id": cid, "caption": pesan[:1000]}, files={"photo": f}, timeout=20)
            else:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                requests.post(url, data={"chat_id": cid, "text": pesan[:4000]}, timeout=20)
        except Exception as e:
            print(f"Gagal kirim ke Telegram ({cid}):", e)

def ambil_4_foto_harian_regu(page, folder_url, putaran_piket):
    """Memindai 40 foto di dalam folder Regu yang bertugas, lalu mengambil 4 foto
    berurutan untuk QW4.1, QW4.2, QW4.3, dan QW4.4 sesuai putaran piketnya."""
    folder_id = folder_url.rstrip("/").split("/")[-1].split("?")[0]
    embed_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"

    file_links = []
    seen = set()
    try:
        res = requests.get(embed_url, timeout=20)
        ids = re.findall(r"/file/d/([a-zA-Z0-9_-]{25,})/", res.text)
        if not ids:
            ids = re.findall(r'id="entry-([a-zA-Z0-9_-]{25,})"', res.text)
        
        for fid in ids:
            if fid != folder_id and fid not in seen:
                seen.add(fid)
                file_links.append(f"https://drive.google.com/file/d/{fid}/view?usp=drivesdk")

        # Cadangan: buka via browser Playwright jika belum terbaca
        if not file_links:
            page.goto(embed_url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            html = page.content()
            ids2 = re.findall(r"/file/d/([a-zA-Z0-9_-]{25,})/", html)
            if not ids2:
                ids2 = re.findall(r'id="entry-([a-zA-Z0-9_-]{25,})"', html)
            for fid in ids2:
                if fid != folder_id and fid not in seen:
                    seen.add(fid)
                    file_links.append(f"https://drive.google.com/file/d/{fid}/view?usp=drivesdk")
    except Exception as e:
        print("Gagal memindai folder Google Drive:", e)

    if file_links:
        total_foto = len(file_links)
        base_idx = putaran_piket * 4  # Setiap kali piket bergeser 4 foto (1-4, 5-8, 9-12, dst.)
        hasil_4_foto = []
        for i in range(4):
            idx_terpilih = (base_idx + i) % total_foto
            hasil_4_foto.append((file_links[idx_terpilih], idx_terpilih + 1, total_foto))
        return hasil_4_foto

    return [(DEFAULT_LINK, i + 1, 1) for i in range(4)]

def jalankan_robot_spkt():
    data_regu, putaran_piket = hitung_jadwal_regu_hari_ini()
    nomor_regu = data_regu["regu"]
    nama_petugas = data_regu["nama"]
    folder_url = data_regu["folder_url"]

    kirim_notif_telegram(
        f"🤖 Robot SPKT Polsek Jatisrono mulai berjalan...\n"
        f"👮 Piket Hari Ini: Regu {nomor_regu} ({nama_petugas})\n"
        f"🔄 Putaran Piket ke-{putaran_piket + 1} (Mengambil 4 foto berurutan dari Folder Regu {nomor_regu})"
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
            # 1. Ambil 4 link foto berbeda dari folder Regu yang sedang piket hari ini
            empat_foto = ambil_4_foto_harian_regu(page, folder_url, putaran_piket)

            # 2. Buka halaman Posko PBM
            page.goto("https://poskopbm.polri.go.id/input", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # 3. Login jika diminta
            if page.locator("input[type='password']").count() > 0:
                page.locator("input[type='email'], input[type='text']").first.fill(EMAIL)
                page.locator("input[type='password']").first.fill(PASSWORD)
                page.get_by_role("button", name="Masuk").click()
                page.wait_for_timeout(5000)

            # 4. Isi Nama Pelapor & Pilih Jabatan "Ka SPKT (6 kegiatan)"
            page.get_by_label("Nama dan pangkat pelapor").fill(nama_petugas)
            page.locator("select").first.select_option(label="Ka SPKT (6 kegiatan)")
            page.wait_for_timeout(2500)

            # 5. Buka daftar kegiatan QW4 (Klik tombol "Isi laporan" urutan pertama untuk QW4)
            if page.get_by_role("button", name="Isi laporan").count() > 0:
                page.get_by_role("button", name="Isi laporan").first.click()
                page.wait_for_timeout(2000)
            else:
                page.get_by_text("110 Respons Cepat").first.click()
                page.wait_for_timeout(2000)

            # 6. Looping isi dan kirim keempat laporan SPKT (QW4.1 s/d QW4.4)
            for idx, item in enumerate(DAFTAR_KEGIATAN_SPKT):
                kode = item["kode"]
                nama_giat = item["nama"]
                link_foto, no_foto, tot_foto = empat_foto[idx]

                # Pastikan daftar QW4.1-QW4.4 terbuka, lalu klik nama kegiatannya
                if not page.get_by_text(nama_giat).first.is_visible():
                    if page.get_by_role("button", name="Isi laporan").count() > 0:
                        page.get_by_role("button", name="Isi laporan").first.click()
                        page.wait_for_timeout(1500)

                page.get_by_text(nama_giat).first.click()
                page.wait_for_timeout(2000)

                # Isi b. Nama dan pangkat pejabat pelaksana
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
                    f"📸 Foto ke-{no_foto} dari {tot_foto} (Folder Regu {nomor_regu})\n"
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
