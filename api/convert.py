import io
from flask import Request, send_file
from docx2pdf import convert as docx2pdf_convert
from PIL import Image
import tempfile

def default(request: Request):
    mode = request.form.get('mode')
    file = request.files.get('file')
    input_format = request.form.get('input_format')
    output_format = request.form.get('output_format')
    # Proses ringan: DOCX ke PDF, JPG ke PNG
    if not file or not input_format or not output_format:
        return {"error": "File dan format harus diisi"}, 400
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
        else:
            return {"error": "Konversi ini hanya didukung untuk proses ringan di Vercel."}, 400
    except Exception as e:
        return {"error": str(e)}, 500
    with open(out_tmp_name, 'rb') as f:
        output_bytes = io.BytesIO(f.read())
    output_bytes.seek(0)
    return send_file(output_bytes, as_attachment=True, download_name=f'converted.{output_format}')
