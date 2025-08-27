from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
import tempfile, os, io
from PIL import Image
from docx2pdf import convert as docx2pdf_convert

app = Flask(__name__)

@app.route('/api/convert', methods=['POST'])
def convert():
    mode = request.form.get('mode')
    file = request.files.get('file')
    input_format = request.form.get('input_format')
    output_format = request.form.get('output_format')
    if not file or not input_format or not output_format:
        return jsonify({'error': 'File dan format harus diisi'}), 400
    input_bytes = file.read()
    with tempfile.NamedTemporaryFile(suffix=f'.{input_format}', delete=False) as in_tmp, tempfile.NamedTemporaryFile(suffix=f'.{output_format}', delete=False) as out_tmp:
        in_tmp.write(input_bytes)
        in_tmp.flush()
        in_tmp_name = in_tmp.name
        out_tmp_name = out_tmp.name
    try:
        # DOCX ke PDF
        if input_format == 'docx' and output_format == 'pdf':
            docx2pdf_convert(in_tmp_name, out_tmp_name)
        # JPG ke PNG
        elif input_format == 'jpg' and output_format == 'png':
            image = Image.open(in_tmp_name)
            image.save(out_tmp_name, 'PNG')
        # Video/Audio conversion dengan ffmpeg
        elif input_format in ['mp4', 'avi', 'mov', 'mkv', 'webm', 'mp3', 'wav', 'aac', 'flac'] and output_format in ['mp4', 'mp3', 'wav', 'aac', 'flac']:
            import subprocess
            subprocess.run(['ffmpeg', '-y', '-i', in_tmp_name, out_tmp_name], check=True)
        # Download video/audio dengan yt-dlp
        elif input_format == 'url' and output_format in ['mp4', 'mp3']:
            import yt_dlp
            ydl_opts = {
                'outtmpl': out_tmp_name,
                'format': 'bestvideo+bestaudio/best' if output_format == 'mp4' else 'bestaudio/best',
                'merge_output_format': output_format if output_format == 'mp4' else None,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': output_format,
                }] if output_format == 'mp3' else []
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([file.filename])
        # PDF ke JPG/PNG (halaman pertama)
        elif input_format == 'pdf' and output_format in ['jpg', 'png']:
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(in_tmp_name, first_page=1, last_page=1)
                images[0].save(out_tmp_name, output_format.upper())
            except ImportError:
                raise Exception('pdf2image library is required for PDF to image conversion.')
        # Fallback universal: copy as-is (rename extension)
        else:
            with open(out_tmp_name, 'wb') as f:
                f.write(input_bytes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    with open(out_tmp_name, 'rb') as f:
        output_bytes = io.BytesIO(f.read())
    output_bytes.seek(0)
    return send_file(output_bytes, as_attachment=True, download_name=f'converted.{output_format}')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
