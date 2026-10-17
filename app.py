import os
import sqlite3
import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory

app = Flask(__name__)
app.secret_key = 'umuttech_guvenli_anahtar'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    conn = sqlite3.connect('main.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            giris_numarasi TEXT PRIMARY KEY,
            giris_sifresi TEXT NOT NULL,
            isim TEXT NOT NULL,
            soyisim TEXT NOT NULL,
            katagori TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            course_name TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            due_date TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id TEXT,
            giris_numarasi TEXT,
            file_path TEXT,
            student_note TEXT,
            submit_date TEXT,
            status TEXT DEFAULT 'Teslim Edilmedi',
            checked_by TEXT,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id),
            FOREIGN KEY (giris_numarasi) REFERENCES users(giris_numarasi)
        )
    ''')
    
    try:
        cursor.execute("ALTER TABLE submissions ADD COLUMN checked_by TEXT")
    except:
        pass

    conn.commit()
    conn.close()

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        giris_numarasi = request.form.get('username', '').strip()
        giris_sifresi = request.form.get('password', '')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE giris_numarasi = ? AND giris_sifresi = ?", 
                       (giris_numarasi, giris_sifresi))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['giris_numarasi'] = user['giris_numarasi']
            session['ad_soyad'] = f"{user['isim']} {user['soyisim']}"
            session['katagori'] = user['katagori']

            if user['katagori'] == 'kontrolcu':
                return redirect(url_for('kontrolcu_panel'))
            elif user['katagori'] == 'ogrenci':
                return redirect(url_for('ogrenci_panel'))
            elif user['katagori'] == 'ogretmen':
                return redirect(url_for('ogretmen_panel'))
            else:
                return redirect(url_for('veriler_yonetim'))
        else:
            flash("Hatalı kullanıcı bilgisi veya şifre!")

    return render_template('login.html')

@app.route('/ogrenci')
def ogrenci_panel():
    if 'giris_numarasi' not in session:
        return redirect(url_for('login'))

    if session.get('katagori') not in ['ogrenci', 'kontrolcu']:
        return redirect(url_for('login'))

    giris_numarasi = session['giris_numarasi']
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT a.id, a.title, a.course_name, a.description, a.created_at, a.due_date,
               s.id as sub_id, s.file_path, s.student_note, s.submit_date, s.status, s.checked_by
        FROM assignments a
        LEFT JOIN submissions s ON a.id = s.assignment_id AND s.giris_numarasi = ?
    ''', (giris_numarasi,))
    
    rows = cursor.fetchall()
    assignments = []
    
    toplam = len(rows)
    yapilan = 0
    yapilmayan = 0
    gec_yapilan = 0

    for r in rows:
        status = r['status']
        is_submitted = status is not None and status != 'Teslim Edilmedi'
        
        if is_submitted:
            yapilan += 1
            if status and 'GEÇ' in status:
                gec_yapilan += 1
        else:
            yapilmayan += 1
            status = 'Teslim Edilmedi'

        is_rejected = status and 'Reddedildi' in status

        assignments.append({
            'id': r['id'],
            'title': r['title'],
            'course_name': r['course_name'],
            'description': r['description'],
            'created_at': r['created_at'],
            'due_date': r['due_date'],
            'file_path': r['file_path'],
            'student_note': r['student_note'],
            'submit_date': r['submit_date'],
            'status': status,
            'checked_by': r['checked_by'],
            'is_submitted': is_submitted,
            'is_rejected': is_rejected
        })

    conn.close()

    stats = {'toplam': toplam, 'yapilan': yapilan, 'yapilmayan': yapilmayan, 'gec': gec_yapilan}
    return render_template('ogrenci.html', student_name=session['ad_soyad'], assignments=assignments, stats=stats)

@app.route('/ogretmen', methods=['GET', 'POST'])
def ogretmen_panel():
    if 'giris_numarasi' not in session or session.get('katagori') != 'ogretmen':
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        title = request.form.get('title')
        course = request.form.get('course')
        desc = request.form.get('desc')
        due = request.form.get('due')
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        odev_id = "".join([str(random.randint(0, 9)) for _ in range(11)])
        cursor.execute("INSERT INTO assignments VALUES (?, ?, ?, ?, ?, ?)", (odev_id, title, course, desc, created_at, due))
        conn.commit()
        conn.close()
        return redirect(url_for('ogretmen_panel'))

    cursor.execute("SELECT * FROM users WHERE katagori = 'ogrenci' ORDER BY giris_numarasi ASC")
    ogrenciler = cursor.fetchall()

    cursor.execute("SELECT * FROM assignments")
    odevler = cursor.fetchall()
    toplam_odev_sayisi = len(odevler)

    ogrenci_listesi_istatistik = []
    
    genel_toplam_gorev = len(ogrenciler) * toplam_odev_sayisi
    stat_teslim_edilen = 0
    stat_teslim_edilmeyen = 0
    stat_gec_teslim = 0

    for ogrenci in ogrenciler:
        o_teslim_edilen = 0
        o_teslim_edilmeyen = 0
        o_gec_teslim = 0

        for odev in odevler:
            cursor.execute("SELECT * FROM submissions WHERE assignment_id = ? AND giris_numarasi = ?", (odev['id'], ogrenci['giris_numarasi']))
            sub = cursor.fetchone()

            if sub and sub['status'] and sub['status'] != 'Teslim Edilmedi':
                o_teslim_edilen += 1
                stat_teslim_edilen += 1
                if 'GEÇ' in sub['status']:
                    o_gec_teslim += 1
                    stat_gec_teslim += 1
            else:
                o_teslim_edilmeyen += 1
                stat_teslim_edilmeyen += 1

        ogrenci_listesi_istatistik.append({
            'numara': ogrenci['giris_numarasi'],
            'ad_soyad': f"{ogrenci['isim']} {ogrenci['soyisim']}",
            'teslim_edilen': o_teslim_edilen,
            'teslim_edilmeyen': o_teslim_edilmeyen,
            'gec_teslim': o_gec_teslim
        })

    cursor.execute('''
        SELECT s.*, a.title as odev_baslik, a.course_name, u.isim, u.soyisim 
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.id
        JOIN users u ON s.giris_numarasi = u.giris_numarasi
        WHERE s.status != 'Teslim Edilmedi'
    ''')
    tum_teslimler = cursor.fetchall()

    conn.close()

    ogrenci_stats = {
        'toplam_gorev': genel_toplam_gorev,
        'teslim_edilen': stat_teslim_edilen,
        'teslim_edilmeyen': stat_teslim_edilmeyen,
        'gec_teslim': stat_gec_teslim
    }

    return render_template('ogretmen.html', ad_soyad=session['ad_soyad'], odevler=odevler, 
                           ogrenci_listesi=ogrenci_listesi_istatistik, ogrenci_stats=ogrenci_stats, tum_teslimler=tum_teslimler)

@app.route('/kontrolcu', methods=['GET', 'POST'])
def kontrolcu_panel():
    if 'giris_numarasi' not in session or session.get('katagori') != 'kontrolcu':
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_assignment':
            title = request.form.get('title')
            course = request.form.get('course')
            desc = request.form.get('desc')
            due = request.form.get('due')
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            odev_id = "".join([str(random.randint(0, 9)) for _ in range(11)])
            cursor.execute("INSERT INTO assignments VALUES (?, ?, ?, ?, ?, ?)", (odev_id, title, course, desc, created_at, due))
            conn.commit()

        elif action in ['onayla', 'reddet']:
            sub_id = request.form.get('sub_id')
            kontrolcu_adi = session.get('ad_soyad')
            
            cursor.execute('''
                SELECT s.*, a.due_date FROM submissions s 
                JOIN assignments a ON s.assignment_id = a.id 
                WHERE s.id = ?
            ''', (sub_id,))
            sub = cursor.fetchone()

            if sub:
                submit_date = sub['submit_date']
                due_date = sub['due_date']
                zaman_durumu = "GEÇ" if submit_date > due_date else "ZAMANINDA"

                if action == 'onayla':
                    new_status = f"Onaylandı - {zaman_durumu}"
                else:
                    new_status = f"Reddedildi - {zaman_durumu}"

                cursor.execute("UPDATE submissions SET status = ?, checked_by = ? WHERE id = ?", (new_status, kontrolcu_adi, sub_id))
                conn.commit()

        conn.close()
        return redirect(url_for('kontrolcu_panel'))

    cursor.execute("SELECT * FROM users WHERE katagori = 'ogrenci' OR giris_numarasi != ?", (session['giris_numarasi'],))
    ogrenciler = cursor.fetchall()

    cursor.execute("SELECT * FROM assignments")
    odevler = cursor.fetchall()

    islem_bekleyenler = []
    tamamlananlar = []

    for ogrenci in ogrenciler:
        for odev in odevler:
            cursor.execute("SELECT * FROM submissions WHERE assignment_id = ? AND giris_numarasi = ?", (odev['id'], ogrenci['giris_numarasi']))
            sub = cursor.fetchone()

            created_at_val = odev['created_at'] if 'created_at' in odev.keys() else '-'

            veri = {
                'sub_id': sub['id'] if sub else None,
                'ogrenci_ad': f"{ogrenci['isim']} {ogrenci['soyisim']}",
                'ogrenci_no': ogrenci['giris_numarasi'],
                'odev': odev['title'],
                'course': odev['course_name'],
                'created_at': created_at_val,
                'due_date': odev['due_date'],
                'status': sub['status'] if sub else 'Teslim Edilmedi',
                'submit_date': sub['submit_date'] if sub else '-',
                'file': sub['file_path'] if sub else None,
                'checked_by': sub['checked_by'] if sub else '-'
            }

            if sub and sub['status'] == 'Beklemede':
                islem_bekleyenler.append(veri)
            elif sub and sub['status'] and ('Onaylandı' in sub['status'] or 'Reddedildi' in sub['status']):
                tamamlananlar.append(veri)

    conn.close()
    return render_template('kontrolcu.html', ad_soyad=session['ad_soyad'], odevler=odevler, 
                           islem_bekleyenler=islem_bekleyenler, tamamlananlar=tamamlananlar)

@app.route('/submit-assignment', methods=['POST'])
def submit_assignment():
    if 'giris_numarasi' not in session:
        return redirect(url_for('login'))

    assignment_id = request.form.get('assignment_id')
    student_note = request.form.get('note')
    file = request.files.get('file')

    if file:
        filename = f"{session['giris_numarasi']}_{assignment_id}_{file.filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        conn = get_db()
        cursor = conn.cursor()

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        status = 'Beklemede'

        cursor.execute("SELECT id FROM submissions WHERE assignment_id = ? AND giris_numarasi = ?", (assignment_id, session['giris_numarasi']))
        existing = cursor.fetchone()

        if existing:
            cursor.execute('''
                UPDATE submissions SET file_path = ?, student_note = ?, submit_date = ?, status = ?, checked_by = NULL
                WHERE assignment_id = ? AND giris_numarasi = ?
            ''', (filename, student_note, now_str, status, assignment_id, session['giris_numarasi']))
        else:
            cursor.execute('''
                INSERT INTO submissions (assignment_id, giris_numarasi, file_path, student_note, submit_date, status, checked_by)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
            ''', (assignment_id, session['giris_numarasi'], filename, student_note, now_str, status))

        conn.commit()
        conn.close()

    return redirect(url_for('ogrenci_panel'))

@app.route('/veriler', methods=['GET', 'POST'])
def veriler_yonetim():
    if 'giris_numarasi' not in session or session.get('katagori') == 'ogrenci':
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_user':
            num = request.form.get('num')
            sifre = request.form.get('sifre')
            isim = request.form.get('isim')
            soyisim = request.form.get('soyisim')
            katagori = request.form.get('katagori')
            try:
                cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", (num, sifre, isim, soyisim, katagori))
                conn.commit()
            except:
                flash("Bu numara zaten kayıtlı!")

        elif action == 'update_user':
            old_num = request.form.get('old_num')
            num = request.form.get('num')
            sifre = request.form.get('sifre')
            isim = request.form.get('isim')
            soyisim = request.form.get('soyisim')
            katagori = request.form.get('katagori')
            cursor.execute("UPDATE users SET giris_numarasi=?, giris_sifresi=?, isim=?, soyisim=?, katagori=? WHERE giris_numarasi=?", 
                           (num, sifre, isim, soyisim, katagori, old_num))
            conn.commit()

        elif action == 'delete_user':
            num = request.form.get('num')
            cursor.execute("DELETE FROM users WHERE giris_numarasi=?", (num,))
            conn.commit()

        elif action == 'add_assignment':
            title = request.form.get('title')
            course = request.form.get('course')
            desc = request.form.get('desc')
            due = request.form.get('due')
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
            odev_id = "".join([str(random.randint(0, 9)) for _ in range(11)])
            cursor.execute("INSERT INTO assignments VALUES (?, ?, ?, ?, ?, ?)", (odev_id, title, course, desc, created_at, due))
            conn.commit()

        elif action == 'update_assignment':
            aid = request.form.get('id')
            title = request.form.get('title')
            course = request.form.get('course')
            desc = request.form.get('desc')
            due = request.form.get('due')
            cursor.execute("UPDATE assignments SET title=?, course_name=?, description=?, due_date=? WHERE id=?", 
                           (title, course, desc, due, aid))
            conn.commit()

        elif action == 'delete_assignment':
            aid = request.form.get('id')
            cursor.execute("DELETE FROM assignments WHERE id=?", (aid,))
            cursor.execute("DELETE FROM submissions WHERE assignment_id=?", (aid,))
            conn.commit()

        elif action == 'update_submission':
            sub_id = request.form.get('sub_id')
            status = request.form.get('status')
            checked_by = request.form.get('checked_by')
            cursor.execute("UPDATE submissions SET status=?, checked_by=? WHERE id=?", (status, checked_by, sub_id))
            conn.commit()

        elif action == 'delete_submission':
            sub_id = request.form.get('sub_id')
            cursor.execute("DELETE FROM submissions WHERE id=?", (sub_id,))
            conn.commit()

        conn.close()
        return redirect(url_for('veriler_yonetim'))

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    cursor.execute("SELECT * FROM assignments")
    assignments = cursor.fetchall()
    cursor.execute('''
        SELECT s.id, a.title, u.isim, u.soyisim, s.status, s.submit_date, s.file_path, s.student_note, s.checked_by
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.id
        JOIN users u ON s.giris_numarasi = u.giris_numarasi
    ''')
    submissions = cursor.fetchall()

    conn.close()
    return render_template('veriler.html', users=users, assignments=assignments, submissions=submissions, ad_soyad=session.get('ad_soyad'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/hizli-giris')
def hizli_giris():
    session['giris_numarasi'] = 'admin_test'
    session['ad_soyad'] = 'Hızlı Admin'
    session['katagori'] = 'ogretmen'
    return redirect(url_for('veriler_yonetim'))

@app.route('/sifre-degistir', methods=['POST'])
def sifre_degistir():
    if 'giris_numarasi' not in session:
        return redirect(url_for('login'))

    eski_sifre = request.form.get('eski_sifre')
    yeni_sifre = request.form.get('yeni_sifre')
    giris_numarasi = session['giris_numarasi']

    conn = get_db()
    cursor = conn.cursor()

    # Mevcut şifreyi kontrol et
    cursor.execute("SELECT giris_sifresi FROM users WHERE giris_numarasi = ?", (giris_numarasi,))
    user = cursor.fetchone()

    if user and user['giris_sifresi'] == eski_sifre:
        cursor.execute("UPDATE users SET giris_sifresi = ? WHERE giris_numarasi = ?", (yeni_sifre, giris_numarasi))
        conn.commit()
        conn.close()
        flash("Şifreniz başarıyla güncellendi!")
    else:
        conn.close()
        flash("Mevcut şifreniz hatalı!")

    # Kullanıcıyı geldiği panele geri yönlendir
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)