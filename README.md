# Learn AI Playground

Proyek belajar kecil: **chat dengan model yang bisa menjalankan kode Python di sandbox**. Backend, frontend, dan sandbox,
sekitar 300 baris semuanya. Ditulis dari nol supaya bisa dibaca dari atas ke bawah dalam satu sore.

## Menjalankan

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload      # buka http://localhost:8000
```

- **Tanpa API key** jalan di *mode demo* (model palsu yang menjalankan kode sungguhan di sandbox). Cukup untuk melihat alurnya.
- **Dengan model asli:** `export ANTHROPIC_API_KEY=...` (PowerShell: `$env:ANTHROPIC_API_KEY="..."`) lalu jalankan ulang.
  Model bisa diganti lewat `MODEL=...` (bawaan `claude-haiku-5-5`).
- Tes: `pytest` (15 tes, tanpa jaringan dan tanpa API key).

## Cara kerjanya

```
browser ──POST /api/chat {messages}──▶ main.py ──▶ agent.py (loop) ◀──▶ llm.py  (model)
   ▲                                                    │
   └──────── SSE: text / tool_call / tool_result / done ┴──▶ tools.py ──▶ sandbox.py (subprocess)
```

1. Browser mengirim **seluruh percakapan**. Server tidak menyimpan apa pun antar permintaan.
2. `agent.py` bertanya ke model. Kalau model minta tool (`run_python`), kodenya dijalankan, hasilnya dikirim balik
   ke model, lalu model ditanya lagi. Berulang sampai model menjawab biasa (maksimal 6 putaran).
3. Setiap langkah dikirim ke browser sebagai event kecil (Server-Sent Events), jadi jawaban muncul sambil ditulis.

| Berkas | Isi | Baca kalau mau paham |
|---|---|---|
| `app/agent.py` | loop agent | inti semuanya, mulai dari sini |
| `app/tools.py` | skema tool + penjalannya | cara model "memanggil fungsi" |
| `app/sandbox.py` | menjalankan kode di subprocess | batas waktu, memori, env bersih |
| `app/llm.py` | klien model + `DemoLLM` | satu antarmuka, dua implementasi |
| `app/main.py` | server, stream SSE | bagaimana event sampai ke browser |
| `static/index.html` | UI satu halaman | membaca stream, kartu tool |

## Penting: sandbox ini BUKAN batas keamanan

Kode model berjalan **sebagai kamu**, di komputermu, dan masih bisa membaca file dan memakai jaringan. Yang ada: folder
sementara, env tanpa API key, batas waktu 10 detik, batas memori 512 MB (Linux/macOS), output dipotong. Itu cukup untuk
belajar di laptop sendiri, **jangan** dipakai untuk orang lain atau data penting. Latihan 3 menggantinya dengan Docker.
Di Windows batas memori tidak aktif (hanya batas waktu).

## Latihan (urut dari mudah)

1. **Baca dan ubah loop.** Ubah `MAX_ROUNDS` jadi 1, tanya "hitung 17*23 pakai python", lihat apa yang terjadi. Kembalikan.
2. **Tambah tool kedua**, misalnya `read_file` yang hanya boleh membaca folder `notes/`. Tambah skemanya di `tools.py`
   dan satu cabang di `run_tool`. Tes: path seperti `../../etc/passwd` harus ditolak.
3. **Sandbox Docker.** Ganti isi `_run` dengan `docker run --rm --network none --memory 256m --cpus 1 python:3.12-slim python ...`.
   Bandingkan: apa yang sekarang tidak bisa dilakukan kode model?
4. **Simpan percakapan** di SQLite (id percakapan di URL), supaya refresh tidak menghapus riwayat.
5. **Dua model.** Model murah untuk pertanyaan ringan dan model kuat untuk yang berat. Mulai dari aturan sederhana
   (panjang pesan, kata kunci), lalu coba klasifikasi dengan embedding.
6. **Streaming yang lebih halus.** Sekarang tool dipanggil setelah model selesai menulis. Coba tampilkan argumen tool
   saat masih ditulis (`input_json_delta` di API streaming).

## Batasan sengaja

Tanpa login, tanpa database, tanpa batas penggunaan, satu pengguna. Riwayat ada di browser, jadi pengguna bisa memalsukannya.
Itu tidak apa-apa untuk belajar dan sengaja dibiarkan supaya kodenya tetap kecil.
