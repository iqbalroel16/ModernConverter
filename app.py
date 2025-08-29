import os
import io
import tempfile
from flask import Flask, render_template, request, send_file, redirect, url_for, flash, session, make_response
from werkzeug.utils import secure_filename
## yt_dlp dan ffmpeg dihapus agar aman untuk shared hosting
import requests
from dotenv import load_dotenv
from mimetypes import guess_type
from functools import wraps
# Tambahan untuk dokumen
from pdf2docx import Converter as PDF2DocxConverter
from docx2pdf import convert as docx2pdf_convert
from PIL import Image
import uuid

load_dotenv()

app = Flask(__name__, static_url_path='/public', static_folder='public')
app.secret_key = os.urandom(24)

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent'
USAGE_LOG = 'usage.log'

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

# In-memory cache untuk file hasil konversi (RAM, bukan session/cookie)
file_cache = {}

# Decorator for admin login required
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET', 'POST'])
def index():
    mode = request.form.get('mode', 'link')
    if request.method == 'POST':
        mode = request.form.get('mode')
        link = request.form.get('link')
        file = request.files.get('file')
        output_format = request.form.get('output_format')
        input_format = request.form.get('input_format')
        doc_format = request.form.get('doc_format')
        quality = request.form.get('quality')
        gemini_feature = request.form.get('gemini_feature')
        site = request.form.get('site')
        result = None
        output_bytes = None
        output_filename = None
        # Fallback: ambil ekstensi file jika input_format/output_format kosong
        if file and (not input_format or not output_format):
            filename = file.filename
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            if not input_format:
                input_format = ext
            if not output_format:
                output_format = ext
        # Validasi format file yang diupload
        if file and input_format:
            filename = file.filename
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            if ext != input_format:
                flash(f"Format file yang diupload ({ext}) tidak sesuai dengan pilihan format asal ({input_format}). Silakan pilih format yang sesuai.")
                return render_template('index.html', mode=mode)
        # Blokir link YouTube
        if mode == 'link' and link and ('youtube.com' in link or 'youtu.be' in link):
            flash('Maaf, untuk link YouTube tidak kami sediakan sesuai kebijakan Google demi keamanan aplikasi. Silakan gunakan link lain.')
            return render_template('index.html', mode=mode)
        # Link recognition logic
        if mode == 'link' and link:
            output_bytes, output_filename = download_from_link_memory(link, output_format, quality)
        elif mode == 'file' and file:
            output_bytes, output_filename = convert_file_memory(file, input_format, output_format)
        elif mode == 'document' and file:
            output_bytes, output_filename = convert_document_memory(file, input_format, output_format)
        if output_bytes:
            if gemini_feature:
                result = gemini_analyze(output_filename, gemini_feature)
            # Simpan file ke cache RAM dengan ID unik
            file_id = str(uuid.uuid4())
            file_cache[file_id] = (output_bytes.getvalue(), output_filename)
            return render_template('index.html', download_url=url_for('download_file_mem', file_id=file_id), result=result, mode=mode)
        else:
            flash('Please provide a valid input.')
    return render_template('index.html', mode=mode)

def download_from_link_memory(link, output_format, quality):
    import re
    import unicodedata
    import tempfile
    try:
        import yt_dlp
    except ImportError:
        return None, None
    def safe_filename(s):
        s = unicodedata.normalize('NFKD', s)
        s = re.sub(r'[\\/:*?"<>|]', '', s)
        s = re.sub(r'[\uD800-\uDBFF][\uDC00-\uDFFF]', '', s)
        s = s.replace('？', '').replace('#', '').replace(' ', '_')
        s = ''.join(c for c in s if c.isprintable())
        return s
    with tempfile.TemporaryDirectory() as tmpdir:
        if output_format == 'mp3':
            ydl_opts = {
                'outtmpl': f'{tmpdir}/%(title)s.%(ext)s',
                'format': 'bestaudio/best',
                'postprocessors': [
                    {
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                    }
                ],
            }
        elif output_format == 'mp4':
            if quality and quality.isdigit():
                ydl_format = f'bestvideo[height<={quality}]+bestaudio/best/best[height<={quality}]'
            else:
                ydl_format = 'bestvideo+bestaudio/best'
            ydl_opts = {
                'outtmpl': f'{tmpdir}/%(title)s.%(ext)s',
                'format': ydl_format,
                'merge_output_format': 'mp4',
            }
        else:
            ydl_opts = {
                'outtmpl': f'{tmpdir}/%(title)s.%(ext)s',
                'format': 'bestvideo+bestaudio/best',
            }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
            if not files:
                return None, None
            largest_file = max(files, key=os.path.getsize)
            output_filename = os.path.basename(largest_file)
            with open(largest_file, 'rb') as f:
                file_content = f.read()
            output_bytes = io.BytesIO(file_content)
            output_bytes.seek(0)
            return output_bytes, output_filename

def convert_file_memory(file, input_format, output_format):
    import tempfile
    input_bytes = file.read()
    with tempfile.NamedTemporaryFile(suffix=f'.{input_format}', delete=False) as in_tmp, tempfile.NamedTemporaryFile(suffix=f'.{output_format}', delete=False) as out_tmp:
        in_tmp.write(input_bytes)
        in_tmp.flush()
        in_tmp_name = in_tmp.name
        out_tmp_name = out_tmp.name
    try:
        # Video/Audio conversion with ffmpeg
        if input_format in ['mp4', 'avi', 'mov', 'mkv', 'webm', 'mp3', 'wav', 'aac', 'flac'] and output_format in ['mp4', 'mp3', 'wav', 'aac', 'flac']:
            import subprocess
            cmd = [
                'ffmpeg', '-y', '-i', in_tmp_name, out_tmp_name
            ]
            subprocess.run(cmd, check=True)
        # Image conversion with PIL
        elif input_format in ['jpg', 'jpeg', 'png', 'bmp', 'gif'] and output_format in ['jpg', 'jpeg', 'png', 'bmp', 'gif']:
            from PIL import Image
            image = Image.open(in_tmp_name)
            image.save(out_tmp_name, output_format.upper())
        # Fallback: copy as-is if format sama
        elif input_format == output_format:
            with open(out_tmp_name, 'wb') as f:
                f.write(input_bytes)
        else:
            # Fallback universal: copy as-is (rename extension)
            with open(out_tmp_name, 'wb') as f:
                f.write(input_bytes)
    except Exception as e:
        return None, None
    # Baca hasil output
    with open(out_tmp_name, 'rb') as f:
        output_bytes = io.BytesIO(f.read())
    output_bytes.seek(0)
    output_filename = file.filename.rsplit('.', 1)[0] + f'.{output_format}'
    # Bersihkan file temp
    try:
        os.remove(in_tmp_name)
        os.remove(out_tmp_name)
    except Exception:
        pass
    return output_bytes, output_filename

def convert_document_memory(file, input_format, output_format):
    # Konversi dokumen di memori menggunakan tempfile, hasil langsung ke BytesIO
    input_bytes = file.read()
    with tempfile.NamedTemporaryFile(suffix=f'.{input_format}', delete=False) as in_tmp, tempfile.NamedTemporaryFile(suffix=f'.{output_format}', delete=False) as out_tmp:
        in_tmp.write(input_bytes)
        in_tmp.flush()
        in_tmp_name = in_tmp.name
        out_tmp_name = out_tmp.name
    # Tutup file agar tidak locked oleh proses lain (penting untuk Windows/COM)
    try:
        import subprocess
        subprocess.run(["unoconv", "-f", output_format, "-o", out_tmp_name, in_tmp_name], check=True)
    except Exception:
        # Fallback: PDF ke DOCX
        if input_format == 'pdf' and output_format == 'docx':
            cv = PDF2DocxConverter(in_tmp_name)
            cv.convert(out_tmp_name)
            cv.close()
        # DOCX ke PDF
        elif input_format == 'docx' and output_format == 'pdf':
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
            docx2pdf_convert(in_tmp_name, out_tmp_name)
        # JPG/PNG ke PDF
        elif input_format in ['jpg', 'jpeg', 'png'] and output_format == 'pdf':
            image = Image.open(in_tmp_name)
            image.save(out_tmp_name, 'PDF', resolution=100.0)
        # PDF ke JPG/PNG (halaman pertama)
        elif input_format == 'pdf' and output_format in ['jpg', 'png']:
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(in_tmp_name, first_page=1, last_page=1)
                images[0].save(out_tmp_name, output_format.upper())
            except ImportError:
                raise Exception('pdf2image library is required for PDF to image conversion.')
        # Tambahan: fallback konversi file binary (copy as-is jika format sama)
        elif input_format == output_format:
            with open(out_tmp_name, 'wb') as f:
                f.write(input_bytes)
        else:
            # Fallback universal: copy as-is (rename extension)
            with open(out_tmp_name, 'wb') as f:
                f.write(input_bytes)
    # Baca hasil output
    with open(out_tmp_name, 'rb') as f:
        output_bytes = io.BytesIO(f.read())
    output_bytes.seek(0)
    output_filename = file.filename.rsplit('.', 1)[0] + f'.{output_format}'
    # Bersihkan file temp
    try:
        os.remove(in_tmp_name)
    except Exception:
        pass
    try:
        os.remove(out_tmp_name)
    except Exception:
        pass
    return output_bytes, output_filename

@app.route('/download_mem/<file_id>')
def download_file_mem(file_id):
    file_data = file_cache.pop(file_id, None)  # Hapus dari cache setelah diunduh
    if not file_data:
        flash('File tidak ditemukan atau sudah diunduh. Silakan ulangi proses convert.')
        return redirect(url_for('index'))
    output_bytes, output_filename = file_data
    return send_file(
        io.BytesIO(output_bytes),
        as_attachment=True,
        download_name=output_filename
    )

def gemini_analyze(filename, feature):
    # Example: send file info to Gemini API for summary/description
    headers = {'Content-Type': 'application/json'}
    data = {
        'contents': [{
            'parts': [{
                'text': f'Analyze this file for {feature}: {filename}'
            }]
        }]
    }
    params = {'key': GEMINI_API_KEY}
    response = requests.post(GEMINI_API_URL, headers=headers, params=params, json=data)
    if response.ok:
        return response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    return 'No result from Gemini.'

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials!')
    return render_template('admin_login.html')

    @app.route('/panduan')
    def panduan():
        return render_template('panduan.html')

    @app.route('/syarat')
    def syarat():
        return render_template('syarat.html')

    @app.route('/privacy')
    def privacy():
        return render_template('privacy.html')

    @app.route('/faq')
    def faq():
        return render_template('faq.html')

    @app.route('/about_us')
    def about_us():
        return render_template('about_us.html')

    @app.route('/contact_us', methods=['GET', 'POST'])
    def contact_us():
        if request.method == 'POST':
            # Simpan pesan atau kirim email, dsb (dummy)
            flash('Pesan Anda berhasil dikirim!')
            return redirect(url_for('contact_us'))
        return render_template('contact_us.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    usage_count = 0
    if os.path.exists(USAGE_LOG):
        with open(USAGE_LOG, 'r') as f:
            usage_count = len(f.readlines())
    return render_template('admin_dashboard.html', usage_count=usage_count)

@app.route('/about')
def about():
    return render_template('about.html')
@app.route('/remaster', methods=['GET', 'POST'])
def remaster_image():
    result = None
    output_bytes = None
    output_filename = None
    if request.method == 'POST':
        file = request.files.get('image')
        if not file:
            flash('Silakan upload gambar terlebih dahulu.')
            return render_template('index.html', remaster_result=None)
        try:
            # Proses remaster dengan PIL (enhance, sharpen, dsb)
            from PIL import Image, ImageEnhance, ImageFilter
            image = Image.open(file.stream)
            # Enhance sharpness dan contrast
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(2.0)
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.3)
            # Optional: AI Gemini (jika API tersedia)
            # if GEMINI_API_KEY:
            #     ... panggil Gemini API untuk remaster ...
            output_bytes = io.BytesIO()
            image.save(output_bytes, format='PNG')
            output_bytes.seek(0)
            output_filename = 'remastered_' + file.filename.rsplit('.', 1)[0] + '.png'
            return send_file(output_bytes, as_attachment=True, download_name=output_filename, mimetype='image/png')
        except Exception as e:
            flash('Gagal remaster gambar: ' + str(e))
            return render_template('index.html', remaster_result=None)
    return render_template('index.html', remaster_result=None)

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/donasi')
def donasi():
    return render_template('donasi.html')

if __name__ == '__main__':
    app.run(debug=True)
