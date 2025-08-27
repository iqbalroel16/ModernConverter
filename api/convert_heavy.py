import requests
from flask import Request, jsonify

def handler(request: Request):
    mode = request.form.get('mode')
    file = request.files.get('file')
    input_format = request.form.get('input_format')
    output_format = request.form.get('output_format')
    # Endpoint API eksternal (misal VPS Flask Anda)
    EXTERNAL_API = 'https://your-flask-server.com/api/convert'
    if not file or not input_format or not output_format:
        return {"error": "File dan format harus diisi"}, 400
    files = {'file': (file.filename, file.stream, file.mimetype)}
    data = {
        'mode': mode,
        'input_format': input_format,
        'output_format': output_format
    }
    try:
        resp = requests.post(EXTERNAL_API, files=files, data=data)
        if resp.ok:
            # Return file from external API
            return resp.content, resp.status_code, resp.headers.items()
        else:
            return jsonify({"error": resp.text}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
