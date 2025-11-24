from flask import Flask, render_template, request, jsonify, send_file, stream_with_context, send_from_directory
import yt_dlp
import os
import threading
from datetime import datetime
import logging
from pathlib import Path
import json

app = Flask(__name__)

# Configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.expanduser('~'), 'Downloads', 'YouTube_Downloads')
app.config['MAX_CONTENT_LENGTH'] = 5000 * 1024 * 1024  # 5GB max

# Create downloads folder if it doesn't exist
Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store download progress
download_progress = {}

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/images/<path:filename>')
def serve_images(filename):
    # Serve images from the repository-level `images/` folder so templates
    # referencing `/images/...` work without moving files into `static/`.
    images_dir = os.path.join(app.root_path, 'images')
    return send_from_directory(images_dir, filename)

@app.route('/api/search-resolutions', methods=['POST'])
def search_resolutions():
    """Search for available resolutions"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True,
            'socket_timeout': 30
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
                    res_str = f'{height}p'
                    if res_str not in resolutions:
                        resolutions.append(res_str)
            
            resolutions.sort(key=lambda x: int(x[:-1]), reverse=True)
            
            return jsonify({
                'resolutions': resolutions,
                'title': title,
                'duration': duration,
                'thumbnail': thumbnail,
                'count': len(resolutions)
            })
    
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return jsonify({'error': f'Failed to fetch video info: {str(e)[:100]}'}), 400

@app.route('/api/download', methods=['POST'])
def download():
    """Download video or audio with progress streaming"""
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
            format_str = f'best[height={resolution[:-1]}]'
        else:  # Audio
            format_str = 'bestaudio/best'
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
        Path(temp_folder).mkdir(parents=True, exist_ok=True)
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percent = round((downloaded / total) * 100)
                    logger.info(f"Download progress: {percent}% ({downloaded}/{total})")
        
        ydl_opts = {
            'format': format_str,
            'outtmpl': os.path.join(temp_folder, f'%(title)s_{timestamp}.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }] if download_type == 'Audio' else []
        }
        
        try:
            filename = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
            
            # If downloading audio, look for mp3 file
            if download_type == 'Audio':
                mp3_path = os.path.splitext(filename)[0] + '.mp3'
                if os.path.exists(mp3_path):
                    filename = mp3_path
            
            if not os.path.exists(filename):
                return jsonify({'error': 'Download file not found after download'}), 500
            
            # Stream file with progress
            def generate():
                with open(filename, 'rb') as f:
                    file_size = os.path.getsize(filename)
                    chunk_size = 1024 * 1024  # 1MB chunks
                    sent = 0
                    
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        sent += len(chunk)
                        yield chunk
                
                # Clean up temp file after sending
                try:
                    os.remove(filename)
                except:
                    pass
            
            return app.response_class(
                response=generate(),
                status=200,
                mimetype='application/octet-stream',
                headers={
                    'Content-Disposition': f'attachment; filename="{os.path.basename(filename)}"',
                    'Content-Length': str(os.path.getsize(filename))
                }
            )
        
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"Download error: {str(e)}")
            return jsonify({'error': f'Download failed: {str(e)[:100]}'}), 400
        except Exception as e:
            logger.error(f"Unexpected error during download: {str(e)}")
            return jsonify({'error': f'Download error: {str(e)[:100]}'}), 500
    
    except Exception as e:
        logger.error(f"Request handling error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Page not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error occurred'}), 500

if __name__ == '__main__':
    # For production, use a proper WSGI server
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)