from flask import Flask, render_template, request, jsonify, send_from_directory
import yt_dlp
import os
import threading
from datetime import datetime
import logging
from pathlib import Path
import json

# Load environment variables from a .env file in development
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)

# ------------------- Config -------------------
default_upload = os.path.join(os.path.expanduser('~'), 'Downloads', 'YouTube_Downloads')
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', default_upload)
app.config['MAX_CONTENT_LENGTH'] = int(
    os.environ.get('MAX_CONTENT_LENGTH', 5000 * 1024 * 1024)
)

Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)

# ------------------- Logging -------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------- yt‑dlp options -------------------
def get_ydl_opts_base():
    """Base yt‑dlp options with cookie support for smooth downloads."""
    opts = {
        "nocheckcertificate": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "socket_timeout": 30,
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],
            }
        }
    }
    
    # Add cookies if available - critical for bypassing bot detection
    cookies_file = os.path.join(app.root_path, 'cookies.txt')
    if os.path.exists(cookies_file):
        opts['cookiefile'] = cookies_file
    
    return opts

# ------------------- Routes -------------------
@app.route('/images/<path:filename>')
def serve_images(filename):
    """Serve static images from the repository-level ``images/`` folder."""
    images_dir = os.path.join(app.root_path, 'images')
    return send_from_directory(images_dir, filename)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ping')
def ping():
    """Health‑check endpoint."""
    return jsonify({"status": "ok"})

@app.route('/api/search-resolutions', methods=['POST'])
def search_resolutions():
    """Return available video resolutions for a given YouTube URL."""
    try:
        data = request.json
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400

        ydl_opts = {
            **get_ydl_opts_base(),
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            formats = info.get('formats', [])
            title = info.get('title', 'Video')
            duration = info.get('duration', 0)
            thumbnail = info.get('thumbnail', '')

            resolutions = []
            for fmt in formats:
                height = fmt.get('height')
                if height and height > 0:
                    res = f"{height}p"
                    if res not in resolutions:
                        resolutions.append(res)

            resolutions.sort(key=lambda x: int(x[:-1]), reverse=True)

            return jsonify({
                'resolutions': resolutions,
                'title': title,
                'duration': duration,
                'thumbnail': thumbnail,
                'count': len(resolutions),
            })
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return jsonify({'error': 'Failed to fetch video info'}), 400

@app.route('/api/download', methods=['POST'])
def download():
    """Download video or audio and stream to client."""
    try:
        data = request.json
        url = data.get('url', '').strip()
        download_type = data.get('type', 'Video')
        resolution = data.get('resolution', '')

        if not url:
            return jsonify({'error': 'URL required'}), 400

        if download_type == 'Video':
            if not resolution or not resolution.endswith('p'):
                return jsonify({'error': 'Resolution required for video'}), 400
            fmt_str = f'best[height={resolution[:-1]}]'
        else:
            fmt_str = 'bestaudio/best'

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
        Path(temp_folder).mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            **get_ydl_opts_base(),
            'format': fmt_str,
            'outtmpl': os.path.join(temp_folder, f'%(title)s_{timestamp}.%(ext)s'),
            'quiet': False,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }] if download_type == 'Audio' else [],
        }

        filename = None
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if download_type == 'Audio':
            mp3_path = os.path.splitext(filename)[0] + '.mp3'
            if os.path.exists(mp3_path):
                filename = mp3_path

        if not os.path.exists(filename):
            return jsonify({'error': 'Download failed'}), 500

        def generate():
            try:
                with open(filename, 'rb') as f:
                    chunk_size = 1024 * 1024
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
            finally:
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    pass

        return app.response_class(
            response=generate(),
            status=200,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="{os.path.basename(filename)}"',
                'Content-Length': str(os.path.getsize(filename)),
            },
        )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': 'Download failed'}), 500

# ------------------- Error handlers -------------------
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error'}), 500

# ------------------- Run -------------------
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)