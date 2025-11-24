const urlInput = document.getElementById('url');
        const resolutionSelect = document.getElementById('resolution');
        const downloadBtn = document.getElementById('downloadBtn');
        const messageDiv = document.getElementById('message');
        const videoInfo = document.getElementById('videoInfo');
        const videoContent = document.getElementById('videoContent');
        const videoLoading = document.getElementById('videoLoading');
        const videoTitle = document.getElementById('videoTitle');
        const videoDuration = document.getElementById('videoDuration');
        const videoThumbnail = document.getElementById('videoThumbnail');
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const progressPercent = document.getElementById('progressPercent');
        const progressLabel = document.getElementById('progressLabel');
        const typeSelect = document.getElementById('type');
        const resolutionGroup = document.querySelector('.resolution-group');
        const downloadOptions = document.getElementById('downloadOptions');

        function showMessage(text, type = 'info') {
            messageDiv.textContent = text;
            messageDiv.className = `message ${type}`;
            messageDiv.style.display = 'block';
            if (type !== 'error') {
                setTimeout(() => {
                    messageDiv.style.display = 'none';
                }, 4000);
            }
        }

        function formatDuration(seconds) {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = seconds % 60;
            
            if (hours > 0) {
                return `${hours}h ${minutes}m ${secs}s`;
            }
            return `${minutes}m ${secs}s`;
        }

        let searchTimeout;
        let currentUrl = '';

        urlInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            const url = urlInput.value.trim();
            
            if (url.length > 20 && (url.includes('youtube.com') || url.includes('youtu.be'))) {
                downloadOptions.classList.remove('show');
                
                resolutionSelect.innerHTML = '<option value="">Searching...</option>';
                videoLoading.style.display = 'block';
                videoContent.style.display = 'none';
                videoThumbnail.style.display = 'none';
                videoInfo.style.display = 'block';
                searchTimeout = setTimeout(searchResolutions, 800);
            } else {
                downloadOptions.classList.remove('show');
                videoInfo.style.display = 'none';
            }
        });

        async function searchResolutions() {
            try {
                const url = urlInput.value.trim();
                currentUrl = url;
                showMessage('🔍 Searching for available resolutions...', 'info');

                const response = await fetch('/api/search-resolutions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to fetch resolutions');
                }

                if (currentUrl !== url) return;

                resolutionSelect.innerHTML = '<option value="">Select Resolution</option>';
                
                data.resolutions.forEach(res => {
                    const option = document.createElement('option');
                    option.value = res;
                    option.textContent = res;
                    resolutionSelect.appendChild(option);
                });

                if (data.resolutions.length > 0) {
                    resolutionSelect.value = data.resolutions[0];
                }

                videoTitle.textContent = data.title;
                videoDuration.textContent = `Duration: ${formatDuration(data.duration)}`;
                if (data.thumbnail) {
                    videoThumbnail.src = data.thumbnail;
                    videoThumbnail.style.display = 'block';
                }
                videoLoading.style.display = 'none';
                videoContent.style.display = 'flex';
                
                setTimeout(() => {
                    downloadOptions.classList.add('show');
                }, 100);
                
                showMessage(`✅ Found ${data.count} resolutions`, 'success');

            } catch (error) {
                resolutionSelect.innerHTML = '<option value="">Error loading resolutions</option>';
                videoLoading.style.display = 'none';
                downloadOptions.classList.remove('show');
                showMessage(`❌ ${error.message}`, 'error');
            }
        }

        document.getElementById('downloaderForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            if (!resolutionSelect.value && typeSelect.value === 'Video') {
                showMessage('Please select a resolution', 'error');
                return;
            }

            try {
                downloadBtn.disabled = true;
                downloadBtn.innerHTML = '<span class="loading"></span>Starting...';
                progressContainer.style.display = 'block';
                messageDiv.style.display = 'none';

                const response = await fetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: urlInput.value,
                        resolution: resolutionSelect.value,
                        type: typeSelect.value
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Download failed');
                }

                const contentDisposition = response.headers.get('content-disposition');
                let filename = 'download';
                if (contentDisposition) {
                    const matches = contentDisposition.match(/filename="?([^"]*)"?/);
                    if (matches && matches[1]) {
                        filename = matches[1];
                    }
                }

                const contentLength = response.headers.get('content-length');
                let receivedLength = 0;

                const reader = response.body.getReader();
                const chunks = [];

                progressLabel.textContent = 'Downloading...';

                while (true) {
                    const { done, value } = await reader.read();
                    
                    if (done) break;
                    
                    chunks.push(value);
                    receivedLength += value.length;
                    
                    if (contentLength) {
                        const percent = Math.round((receivedLength / contentLength) * 100);
                        progressFill.style.width = percent + '%';
                        progressPercent.textContent = percent + '%';
                        
                        const received = (receivedLength / 1024 / 1024).toFixed(1);
                        const total = (contentLength / 1024 / 1024).toFixed(1);
                        progressLabel.textContent = `Downloaded: ${received}MB / ${total}MB`;
                    }
                }

                const blob = new Blob(chunks);
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                progressFill.style.width = '100%';
                progressPercent.textContent = '100%';
                progressLabel.textContent = '✅ Download complete! Check your downloads folder';
                downloadBtn.innerHTML = 'Download';
                downloadBtn.disabled = false;
                showMessage('✅ Video downloaded successfully!', 'success');

                setTimeout(() => {
                    progressContainer.style.display = 'none';
                    progressFill.style.width = '0%';
                    progressPercent.textContent = '0%';
                    location.reload();
                }, 3000);

            } catch (error) {
                downloadBtn.innerHTML = 'Download';
                downloadBtn.disabled = false;
                progressContainer.style.display = 'none';
                showMessage(`❌ ${error.message}`, 'error');
            }
        });

        typeSelect.addEventListener('change', (e) => {
            if (e.target.value === 'Audio') {
                resolutionGroup.classList.add('hidden');
            } else {
                resolutionGroup.classList.remove('hidden');
            }
        });

        const pasteBtn = document.getElementById('pasteBtn');
        if (pasteBtn) {
            pasteBtn.addEventListener('click', async () => {
                try {
                    if (navigator.clipboard && navigator.clipboard.readText) {
                        const text = await navigator.clipboard.readText();
                        if (text && text.trim().length) {
                            urlInput.value = text.trim();
                            urlInput.dispatchEvent(new Event('input', { bubbles: true }));
                            showMessage('📋 Pasted from clipboard', 'success');
                        } else {
                            showMessage('Clipboard is empty', 'info');
                        }
                    } else {
                        showMessage('Clipboard API not available. Use Ctrl+V to paste.', 'error');
                    }
                } catch (err) {
                    showMessage('Unable to read clipboard: ' + (err && err.message ? err.message : err), 'error');
                }
            });
        }