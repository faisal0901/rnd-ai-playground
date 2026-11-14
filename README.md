# Learn AI Playground

Proyek belajar kecil: **chat dengan model yang bisa menjalankan kode Python di sandbox**. Backend, frontend, dan sandbox,
sekitar 300 baris semuanya. Ditulis dari nol supaya bisa dibaca dari atas ke bawah dalam satu sore.

## Menjalankan

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt    # requirements.txt = hanya yang dipakai app; -dev menambah pytest dan ruff
uvicorn app.main:app --reload          # buka http://localhost:8000
```

Butuh Python 3.10 atau lebih baru.

- **Tanpa API key** jalan di *mode demo* (model palsu yang menjalankan kode sungguhan di sandbox). Cukup untuk melihat alurnya.
- **Dengan model asli:** salin `.env.example` jadi `.env`, isi `ANTHROPIC_API_KEY` (dan `VOYAGE_API_KEY` untuk RAG),
  lalu jalankan ulang. `.env` dibaca otomatis (`python-dotenv`) dan sudah ada di `.gitignore`.
  Model bisa diganti lewat `MODEL=...` (bawaan `claude-haiku-5-5`).
- Tes: `pytest` (134 tes, tanpa jaringan dan tanpa API key; Voyage diganti objek palsu). Lint dan format: `ruff check .` dan `ruff format .`.

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
| `app/config.py` | semua setting dan konstanta di satu tempat | mengubah batas, ukuran chunk, nama model |
| `app/agent.py` | loop agent | inti semuanya, mulai dari sini |
| `app/tools.py` | skema tool + penjalannya | cara model "memanggil fungsi" |
| `app/sandbox.py` | menjalankan kode di subprocess | batas waktu, memori, env bersih |
| `app/llm.py` | klien model + `DemoLLM` | satu antarmuka, dua implementasi |
| `app/main.py` | server, stream SSE | bagaimana event sampai ke browser |
| `static/index.html` | UI satu halaman | membaca stream, kartu tool |
| `app/embeddings.py` | embedding Voyage + embedding demo + reranker | teks jadi vektor, `input_type` |
| `app/chunking.py` | memotong teks panjang | ukuran dan overlap |
| `app/rag.py` | penyimpanan vektor, indexing, pencarian | cosine, top-k, rerank, cache sidik jari |
| `app/documents.py` | file → teks (txt, md, csv, json, log, PDF), nama file aman | satu jalur baca untuk KB dan lampiran |
| `app/kb.py` | simpan, embed, daftar, hapus dokumen knowledge base | upload yang langsung masuk RAG |
| `static/kb.html` | halaman **Knowledge base** (`/kb`) | upload, daftar, hapus, coba cari |
| `docs/` | dokumen contoh (kopi, hewan, cuti), hanya baca | bahan untuk dicari |

## Debug di VS Code

Buka folder proyek di VS Code, pasang ekstensi yang disarankan (muncul sebagai notifikasi; daftarnya di `.vscode/extensions.json`),
dan pilih interpreter dari `.venv` (`Ctrl+Shift+P` → *Python: Select Interpreter*). Lalu di panel **Run and Debug** (`F5`):

| Konfigurasi | Untuk |
|---|---|
| **API (debug)** | menjalankan server di port 8000 dengan debugger; pasang breakpoint di `agent.py`, `tools.py`, `rag.py` |
| **API (debug, step into libraries)** | sama, tapi boleh masuk ke kode pustaka (FastAPI, anthropic, numpy) |
| **Search the docs without the LLM** | menjalankan `python -m app.rag` dengan pertanyaan yang kamu ketik, untuk melihat skor |
| **Tests: current file** | men-debug berkas tes yang sedang terbuka |
| **Debug Tests (Testing panel)** | dipakai ikon debug di panel *Testing* (tes `pytest` sudah terdeteksi otomatis) |

Tempat breakpoint yang enak untuk belajar:
1. `app/agent.py`, baris `async for event in llm.stream(...)`: lihat isi `messages` tiap putaran.
2. `app/tools.py`, `run_tool`: lihat apa yang diminta model.
3. `app/rag.py`, `VectorStore.search`: lihat `scores` dan `order` sebelum dipotong ke `k`.
4. `app/chunking.py`, `chunk_text`: lihat potongan yang terbentuk.

Hal yang perlu diketahui:
- **Jangan pakai `--reload` saat debug.** Reloader menjalankan server di proses anak, dan breakpoint sering tidak kena. Konfigurasi di atas sengaja tanpa `--reload`; ubah kode lalu mulai ulang (`Ctrl+Shift+F5`).
- **Kode yang ditulis model tidak bisa di-debug.** Ia jalan di proses terpisah (`sandbox.py`). Breakpoint di `sandbox.py` sendiri kena.
- Debugger memakai `.env` yang sama dengan app (dibaca `python-dotenv` saat start), jadi tidak perlu mengisi `envFile`.
- Jawaban dari model dikirim sebagai stream; kalau berhenti di breakpoint lama, browser menunggu dan bisa putus. Itu normal.

## RAG: model membaca dokumenmu

Model tidak tahu isi dokumenmu. Jadi sebelum menjawab, kita **cari** potongan yang relevan dan memberikannya sebagai teks.
Di sini pencarian itu adalah **tool** (`search_docs`), jadi model sendiri yang memutuskan kapan perlu mencari. Pola yang sama
dipakai Router MissTika (`search_knowledge_base`), hanya dengan pgvector sebagai penyimpanan.

```
INDEX (sekali per dokumen)                    PENCARIAN (tiap pertanyaan)
docs/*.md ─▶ chunking ─▶ embedding            pertanyaan ─▶ embedding (input_type="query")
              (800 huruf,   (input_type=              │
              overlap 150)   "document")              ▼
                   │                         cosine ke SEMUA vektor ─▶ top 20 ─▶ reranker ─▶ top 5
                   ▼                                                                          │
           VectorStore: matriks numpy + records.json (data/index/)                            ▼
                                                                         tool_result ─▶ model menjawab + sebut sumber
```

Konsep yang perlu dipegang:
- **Embedding** mengubah teks jadi daftar angka (vektor). Teks yang artinya mirip menghasilkan vektor yang arahnya mirip.
- **Cosine similarity** = seberapa searah dua vektor (1 = sama arah, 0 = tidak berhubungan). Vektor sudah dibuat berpanjang 1,
  jadi cukup perkalian titik (`vectors @ query_vector`). Itu seluruh "database vektor"-nya.
- **`input_type`**: dokumen di-embed sebagai `"document"`, pertanyaan sebagai `"query"`. Voyage menambah awalan tersembunyi yang
  berbeda, sehingga pertanyaan lebih dekat ke potongan yang menjawabnya. Tertukar = hasil lebih buruk, tanpa error.
- **Chunking**: satu vektor untuk satu buku mengaburkan semuanya; satu vektor per kata kehilangan konteks. Overlap menjaga
  kalimat yang kebetulan jatuh di titik potong.
- **Model embedding harus sama** antara indexing dan pencarian. Vektor dari model lain hidup di "ruang" berbeda, jadi
  `VectorStore` menolak membuka index yang dibuat model lain.
- **Reranker**: pencarian vektor cepat tapi kasar. Reranker membaca pertanyaan *bersama* tiap kandidat dan menilai ulang. Lebih
  lambat, jadi hanya untuk 20 kandidat teratas.
- **Sidik jari (hash)**: dokumen yang tidak berubah dilewati saat index ulang, jadi tidak membayar embedding dua kali.
- **Dibangun saat pertama dipakai, bukan saat start**: permintaan pertama sedikit lebih lambat, tapi server tidak lambat naik.

## Knowledge base dan lampiran chat: dua jalur yang berbeda

| | Halaman **Knowledge base** (`/kb`) | **Lampirkan** di chat |
|---|---|---|
| Endpoint | `POST /api/kb` | `POST /api/attach` |
| Disimpan di server | ya, di `data/uploads/` | **tidak** |
| Di-embed (masuk RAG) | **ya**, langsung | **tidak** |
| Siapa yang membaca | model, lewat tool `search_docs`, hanya potongan yang relevan | model, **seluruh isi**, di percakapan itu saja |
| Bertahan setelah refresh/restart | ya | tidak (hanya ada di tab dan percakapan itu) |
| Batas | 10 MB per file, 400.000 karakter | 10 MB, tapi teks dipotong di 30.000 karakter |
| Cocok untuk | panduan, SOP, catatan yang dipakai berulang | "ringkas file ini", pertanyaan sekali pakai |

Lampiran chat dikirim ulang di setiap permintaan percakapan (server tidak menyimpan apa pun), jadi file besar membuat tiap
giliran mahal. Itu sebabnya dipotong. Untuk file besar yang sering ditanyakan, pakai Knowledge base: yang dikirim ke model
hanya beberapa potongan.

Yang terjadi saat upload ke `/kb`: nama file dibersihkan (tanpa folder) → teks diambil (PDF lewat `pypdf`) → disimpan →
dipotong → di-embed → indeks disimpan. File yang sama diunggah lagi dilewati (sidik jari). Saat server mulai, isi
`data/uploads/` di-index ulang (file adalah sumber kebenaran; pada mode Voyage indeks tersimpan dipakai dan yang tidak berubah dilewati).
Batas yang ada: PDF hasil scan tidak punya teks (ditolak dengan pesan jelas), PDF berpassword ditolak, tipe lain (.docx, gambar) ditolak.

Mencobanya tanpa LLM:
```bash
python -m app.rag "kopi saya terasa pahit"                    # skor per potongan di terminal
curl "localhost:8000/api/search?q=anjing perlu olahraga&k=3"   # sama, lewat server
curl -X POST localhost:8000/api/index                         # index ulang folder docs/
```

**Mode demo vs Voyage.** Tanpa `VOYAGE_API_KEY`, `DemoEmbedder` hanya mencocokkan *kata*. Coba "anjing itu harus dijalankan tiap hari":
hasilnya salah (kata "hari" cocok dengan dokumen cuti), karena demo tidak tahu "dijalankan" ≈ "diajak jalan". Dengan Voyage, dokumen
hewan seharusnya menang (belum diuji dengan key asli; coba sendiri). Perbedaan itulah gunanya embedding. Nama model bisa diganti lewat `VOYAGE_MODEL` dan `VOYAGE_RERANK_MODEL`
(bawaan `voyage-3.5` dan `rerank-2.5`).

Yang belum teruji: Voyage asli. Tes memakai klien palsu yang memeriksa *apa yang dikirim* (model, `input_type`, batch), bukan
mutu hasilnya. Cobalah dengan key-mu dan bandingkan skor dengan dan tanpa reranker.

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

## Latihan RAG

1. **Lihat sendiri efeknya.** Di `rag.py`, ubah `add_document(..., size=800, overlap=150)` jadi `size=200, overlap=0`, index ulang
   (hapus `data/index/`), lalu tanya hal yang jawabannya melintasi dua paragraf. Apa yang hilang?
2. **Reranker.** Tulis `ReverseReranker`-mu sendiri seperti di `tests/test_rag.py`, lalu bandingkan urutan dengan dan tanpa `VoyageReranker`.
3. **Nomor halaman PDF.** Sekarang semua halaman PDF digabung jadi satu teks. Simpan nomor halaman di setiap potongan
   (`records`) supaya jawaban bisa berbunyi "lihat `laporan.pdf` halaman 7". Apa yang berubah di `chunk_text`?
4. **Metadata filter.** Tambah kolom `tag` per dokumen dan parameter `tag` di `search_docs`, lalu saring sebelum menghitung cosine
   (di Router: `knowledge_filter`).
5. **Hybrid search.** Gabungkan skor vektor dengan pencocokan kata (BM25 sederhana). Di mana kata kunci mengalahkan embedding? (Kode produk, nama orang.)
6. **Ukur kualitasnya.** Buat 15 pasangan (pertanyaan, berkas yang benar), hitung seberapa sering berkas benar ada di top 3 (recall@3).
   Ubah ukuran chunk dan bandingkan angkanya. Tanpa angka, "lebih bagus" hanya perasaan.
7. **Tombol "Simpan ke knowledge base" pada lampiran.** Lampiran sudah dibaca servernya; buat tombol yang mengirim teks itu ke `POST /api/kb`.
   Perhatikan: `add_upload` butuh `bytes` file, jadi apa yang perlu diubah?
8. **OCR untuk PDF scan.** Sekarang ditolak. Tambahkan jalur `pytesseract`, lalu pikirkan: berapa lama OCR 100 halaman? Haruskah upload menunggu? (Router memakai worker terpisah.)
