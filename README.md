# 🎙️ Subtitle Maker — Lightweight Standalone (4GB RAM Ready)

Aplikasi pembuat subtitle mandiri, cepat, dan hemat memori, dirancang khusus agar dapat berjalan mulus di laptop berspesifikasi standar (RAM 4GB ke atas) tanpa koneksi internet dan tanpa dependensi eksternal.

---

## ✨ Fitur & Keunggulan

- ⚡ **Ringan & Hemat RAM (< 250MB)**:
  - Menggunakan model **faster-whisper base (Int8)** yang hanya memakan ~150MB RAM saat inferensi.
  - Bebas dari background service berat, tanpa Docker, tanpa database kompleks.
  - Tidak membebani CPU (pembatasan 2 core thread agar laptop tetap adem dan tidak macet).
- 🧠 **Mandiri 100%**:
  - Model sudah tersimpan lokal di folder `models/faster-whisper/`.
  - Tidak memerlukan download ulang atau koneksi ke folder/aplikasi lain.
- 📝 **Forced Alignment (Akurasi 100% Sesuai Naskah)**:
  - Punya naskah/script sendiri? Cukup tempel di kotak naskah.
  - Sistem akan mencocokkan kata naskah Anda ke ketukan suara audio secara otomatis.
  - Hasil teks 100% sesuai naskah asli tanpa ada kata yang salah dengar!
- 📱 **Preset Khusus Konten Kreator**:
  - **TikTok / Reels / Shorts**: 1 baris, maksimal ~30 karakter (mudah dibaca di layar HP).
  - **Seimbang**: 1 baris, maksimal ~42 karakter.
  - **Standar Netflix / Film**: 2 baris otomatis dengan pemenggalan kata sambung Bahasa Indonesia yang rapi.
- 🎬 **Live Editor & Media Player**:
  - Putar langsung video/audio Anda di web browser dengan subtitle overlay mengambang.
  - Klik baris subtitle mana saja untuk langsung melompat ke detik tersebut di video.
  - Edit teks, atur waktu, dan sinkronkan dengan tombol geser offset (+/- 100ms).
- 💾 **Multi-Format Export**:
  - **SRT** (Standar internasional dengan UTF-8 BOM untuk VLC / Windows Media Player)
  - **VTT** (WebVTT untuk browser/web)
  - **ASS** (Subtitle ber-styling dengan warna pembeda pembicara)
  - **TXT** (Transkrip teks bersih dengan penanda waktu)
  - Salin teks format SRT langsung ke Clipboard dengan satu klik.

---

## 🚀 Cara Menjalankan

### Opsi 1: Klik Ganda (Mode Web Browser - Direkomendasikan)
Cukup klik ganda:
```
📁 C:\Subtitle Maker\
 └── 🟢 start.bat
```
Browser akan otomatis terbuka di `http://localhost:5050`.

### Opsi 2: Mode Terminal (CLI)
Untuk memproses video/audio cepat lewat terminal:
```cmd
cd "C:\Subtitle Maker"
run_cli.bat -i "video.mp4" -l id -m base -c 30
```

---

## 📂 Struktur Direktori Mandiri

```text
C:\Subtitle Maker\
├── app.py              # Server web mandiri & CLI processor
├── start.bat           # Launcher klik ganda
├── run_cli.bat         # Launcher CLI
├── requirements.txt    # Dependensi minimal (faster-whisper, bottle, numpy)
├── README.md           # Petunjuk penggunaan
├── models/             # Folder model Whisper mandiri
│   └── faster-whisper/ # Model base & small lokal
├── engine/             # Modul pemrosesan logika subtitle
│   ├── audio.py        # Ekstraksi cepat FFmpeg
│   ├── aligner.py      # Forced alignment naskah narasi
│   ├── rules.py        # Aturan Netflix / BBC & batas karakter
│   ├── formatter.py    # Formatter SRT, VTT, ASS, TXT
│   ├── transcriber.py  # Pipeline Whisper Int8
│   └── vocabulary.py   # Kamus koreksi kata
├── web/                # Antarmuka Web responsif (HTML, CSS, JS)
├── venv/               # Virtual environment Python lokal
├── temp/               # File sementara pemrosesan
└── output/             # Folder hasil subtitle yang diekspor
```
