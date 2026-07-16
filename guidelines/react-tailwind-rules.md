Aturan Wajib Pengembangan React dan TailwindCSS di Proyek AI-Telebot

Ketika mengembangkan UI berbasis React, ikuti pedoman tegas berikut:
1. PADDING & MARGIN: Selalu gunakan spasi yang lapang. Minimal `p-4` atau `p-6` untuk container. Jangan membuat UI yang terlalu rapat.
2. ROUNDING & SHADOWS: Gunakan `rounded-xl` atau `rounded-2xl` untuk semua kartu (cards) dan tombol. Jangan pakai `rounded-sm`. Tambahkan `shadow-md` atau `shadow-lg` agar elemen terlihat menonjol.
3. COLORS: Jangan pernah gunakan warna generik bawaan browser. Gunakan Tailwind palette (contoh: `bg-slate-900 text-slate-100` untuk dark mode, atau `bg-indigo-600` untuk tombol primary).
4. INTERACTIVITY: Setiap tombol (`button`) WAJIB memiliki efek `hover:` dan `transition-all duration-300`. Contoh: `hover:scale-105 hover:bg-indigo-700`.
5. STATE MANAGEMENT: Tampilkan indikator `Loading...` yang jelas jika sedang melakukan *fetch* data dari backend. Jangan biarkan layar kosong tanpa feedback.
