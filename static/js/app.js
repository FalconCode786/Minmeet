/**
 * Meeting Minutes Application
 * Main application logic, SSE handling, and UI updates.
 * Designed for serverless deployment with polling fallback.
 */

class MeetingApp {
    constructor() {
        this.audioHandler = new AudioHandler();
        this.meetingId = null;
        this.meetingTitle = '';
        this.startTime = null;
        this.durationInterval = null;
        this.eventSource = null;
        this.pollingInterval = null;
        this.transcriptData = [];
        this.qaData = [];
        this.isActive = false;
        
        this.ui = {
            setupScreen: document.getElementById('setup-screen'),
            meetingScreen: document.getElementById('meeting-screen'),
            completionScreen: document.getElementById('completion-screen'),
            startBtn: document.getElementById('start-btn'),
            stopBtn: document.getElementById('stop-btn'),
            titleInput: document.getElementById('meeting-title'),
            activeTitle: document.getElementById('active-title'),
            duration: document.getElementById('duration'),
            participantCount: document.getElementById('participant-count'),
            transcriptContainer: document.getElementById('transcript-container'),
            qaContainer: document.getElementById('qa-container'),
            qaCount: document.getElementById('qa-count'),
            transcriptStatus: document.getElementById('transcript-status'),
            audioCanvas: document.getElementById('audio-canvas'),
            downloadBtn: document.getElementById('download-btn'),
            newMeetingBtn: document.getElementById('new-meeting-btn'),
            meetingSummary: document.getElementById('meeting-summary')
        };

        this.init();
    }

    init() {
        // Event listeners
        this.ui.startBtn.addEventListener('click', () => this.startMeeting());
        this.ui.stopBtn.addEventListener('click', () => this.stopMeeting());
        this.ui.newMeetingBtn.addEventListener('click', () => this.reset());

        // Setup audio visualization
        this.setupVisualizer();

        // Check for existing meeting in URL
        const urlParams = new URLSearchParams(window.location.search);
        const meetingId = urlParams.get('meeting');
        if (meetingId) {
            this.joinExistingMeeting(meetingId);
        }
    }

    setupVisualizer() {
        const canvas = this.ui.audioCanvas;
        const ctx = canvas.getContext('2d');
        
        // Handle high DPI displays
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);

        this.audioHandler.onVisualizerData = (frequencyData, average) => {
            const width = rect.width;
            const height = rect.height;
            
            ctx.clearRect(0, 0, width, height);
            
            // Draw simple bar visualization
            const bars = 30;
            const barWidth = width / bars;
            const step = Math.floor(frequencyData.length / bars);
            
            for (let i = 0; i < bars; i++) {
                const value = frequencyData[i * step];
                const percent = value / 255;
                const barHeight = height * percent * 0.8;
                
                const x = i * barWidth;
                const y = height - barHeight;
                
                // Gradient color based on intensity
                const hue = 200 + (percent * 60); // Blue to purple
                ctx.fillStyle = `hsla(${hue}, 70%, 50%, ${0.3 + percent * 0.7})`;
                ctx.fillRect(x + 1, y, barWidth - 2, barHeight);
            }
        };
    }

    async startMeeting() {
        try {
            this.meetingTitle = this.ui.titleInput.value || 'Untitled Meeting';
            
            // Initialize audio
            this.ui.startBtn.disabled = true;
            this.ui.startBtn.textContent = 'Initializing...';
            
            await this.audioHandler.initialize();

            // Create meeting on server
            const response = await fetch('/api/meetings/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: this.meetingTitle })
            });

            if (!response.ok) throw new Error('Failed to start meeting');

            const data = await response.json();
            this.meetingId = data.meeting_id;
            this.startTime = new Date();

            // Update URL without reload
            window.history.pushState({}, '', `?meeting=${this.meetingId}`);

            // Switch UI
            this.showScreen('meeting');
            this.ui.activeTitle.textContent = this.meetingTitle;
            this.startDurationTimer();

            // Start audio recording
            this.audioHandler.startRecording((blob, isFinal) => {
                this.uploadAudioChunk(blob, isFinal);
            });

            // Start real-time updates
            this.startRealtimeUpdates();

            this.isActive = true;

        } catch (error) {
            console.error('Start meeting error:', error);
            alert('Failed to start meeting: ' + error.message);
            this.ui.startBtn.disabled = false;
            this.ui.startBtn.textContent = 'Start Recording';
        }
    }

    async uploadAudioChunk(blob, isFinal = false) {
        if (!this.meetingId) return;

        const formData = new FormData();
        formData.append('audio', blob, `chunk_${Date.now()}.webm`);
        formData.append('timestamp', Date.now() / 1000);
        formData.append('is_final', isFinal);

        try {
            const response = await fetch(`/api/meetings/${this.meetingId}/audio`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                console.error('Failed to upload audio chunk');
            }
        } catch (error) {
            console.error('Audio upload error:', error);
        }
    }

    startRealtimeUpdates() {
        // Try Server-Sent Events first
        if (typeof EventSource !== 'undefined') {
            this.connectSSE();
        } else {
            // Fallback to polling
            this.startPolling();
        }
    }

    connectSSE() {
        try {
            this.eventSource = new EventSource(`/api/meetings/${this.meetingId}/stream`);

            this.eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleUpdate(data);
            };

            this.eventSource.onerror = (error) => {
                console.log('SSE error, falling back to polling');
                this.eventSource.close();
                this.startPolling();
            };

        } catch (e) {
            this.startPolling();
        }
    }

    startPolling() {
        // Poll every 3 seconds as fallback
        this.pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/meetings/${this.meetingId}/minutes`);
                if (response.ok) {
                    const data = await response.json();
                    this.handleUpdate(data);
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 3000);
    }

    handleUpdate(data) {
        if (data.error) {
            console.error('Update error:', data.error);
            return;
        }

        if (data.status === 'completed') {
            this.handleMeetingComplete();
            return;
        }

        // Update transcript
        if (data.transcript && data.transcript.length > 0) {
            this.appendTranscript(data.transcript);
        }

        // Update Q&A
        if (data.qa_pairs && data.qa_pairs.length > 0) {
            this.updateQADisplay(data.qa_pairs);
        }

        // Update participant count
        if (data.total_speakers) {
            this.ui.participantCount.textContent = 
                `${data.total_speakers} participant${data.total_speakers !== 1 ? 's' : ''}`;
        }

        // Update status
        if (data.transcript && data.transcript.length > 0) {
            this.ui.transcriptStatus.textContent = 'Transcribing...';
            setTimeout(() => {
                this.ui.transcriptStatus.textContent = 'Listening...';
            }, 1000);
        }
    }

    appendTranscript(entries) {
        const container = this.ui.transcriptContainer;
        
        // Remove empty state if present
        const emptyState = container.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        entries.forEach(entry => {
            // Check if already displayed
            if (this.transcriptData.some(e => e.id === entry.id)) return;
            this.transcriptData.push(entry);

            const div = document.createElement('div');
            div.className = `transcript-entry ${entry.is_question ? 'question' : ''}`;
            div.innerHTML = `
                <div class="entry-header">
                    <span class="speaker-name">${this.escapeHtml(entry.speaker)}</span>
                    <span class="entry-time">${this.formatTime(entry.timestamp)}</span>
                </div>
                <div class="entry-text">${this.escapeHtml(entry.text)}</div>
                ${entry.is_question ? '<div class="entry-type">Question detected</div>' : ''}
            `;
            
            container.appendChild(div);
            div.scrollIntoView({ behavior: 'smooth', block: 'end' });
        });
    }

    updateQADisplay(qaPairs) {
        const container = this.ui.qaContainer;
        
        // Clear and rebuild for simplicity (could be optimized for incremental updates)
        container.innerHTML = '';
        
        if (qaPairs.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No questions detected yet</p></div>';
            this.ui.qaCount.textContent = '0';
            return;
        }

        this.ui.qaCount.textContent = qaPairs.length;

        qaPairs.forEach(qa => {
            const q = qa.question || {};
            const answers = qa.answers || [];
            
            const div = document.createElement('div');
            div.className = 'qa-item';
            
            let answersHtml = '';
            answers.forEach(ans => {
                answersHtml += `
                    <div class="answer-item">
                        <div class="answer-label">${this.escapeHtml(ans.speaker)} • ${this.formatTime(ans.timestamp)}</div>
                        <div class="answer-text">${this.escapeHtml(ans.text)}</div>
                    </div>
                `;
            });

            div.innerHTML = `
                <div class="question-block">
                    <div class="question-label">Q • ${this.escapeHtml(q.asked_by || 'Unknown')} • ${this.formatTime(q.timestamp)}</div>
                    <div class="question-text">${this.escapeHtml(q.text || '')}</div>
                </div>
                ${answers.length > 0 ? `<div class="answer-block">${answersHtml}</div>` : '<div class="answer-block"><div class="answer-item"><div class="answer-text" style="font-style: italic; opacity: 0.6;">Waiting for answers...</div></div></div>'}
                ${qa.resolved ? '<div class="resolved-indicator">✓ Resolved</div>' : ''}
            `;
            
            container.appendChild(div);
        });

        container.scrollTop = container.scrollHeight;
    }

    async stopMeeting() {
        if (!this.isActive) return;
        
        this.ui.stopBtn.disabled = true;
        this.ui.stopBtn.textContent = 'Finalizing...';

        // Stop audio
        this.audioHandler.stopRecording();

        // Stop updates
        if (this.eventSource) {
            this.eventSource.close();
        }
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }

        // Call stop endpoint
        try {
            const response = await fetch(`/api/meetings/${this.meetingId}/stop`, {
                method: 'POST'
            });

            if (response.ok) {
                const data = await response.json();
                this.handleMeetingComplete(data);
            } else {
                throw new Error('Failed to stop meeting');
            }
        } catch (error) {
            console.error('Stop meeting error:', error);
            alert('Error finalizing meeting. Please try again.');
            this.ui.stopBtn.disabled = false;
            this.ui.stopBtn.textContent = 'End Meeting';
        }

        this.isActive = false;
    }

    handleMeetingComplete(data) {
        this.stopDurationTimer();
        
        // Show completion screen
        this.showScreen('completion');
        
        // Setup download link
        this.ui.downloadBtn.href = `/api/meetings/${this.meetingId}/pdf`;
        
        // Generate summary
        const duration = this.calculateDuration();
        const summary = `
            <div class="summary-row">
                <span class="summary-label">Meeting Title</span>
                <span class="summary-value">${this.escapeHtml(this.meetingTitle)}</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Duration</span>
                <span class="summary-value">${duration}</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Transcript Entries</span>
                <span class="summary-value">${this.transcriptData.length}</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Questions Asked</span>
                <span class="summary-value">${this.ui.qaCount.textContent}</span>
            </div>
        `;
        this.ui.meetingSummary.innerHTML = summary;
    }

    reset() {
        // Reset state
        this.meetingId = null;
        this.transcriptData = [];
        this.qaData = [];
        this.startTime = null;
        
        // Clear UI
        this.ui.transcriptContainer.innerHTML = '<div class="empty-state"><p>Waiting for speech...</p></div>';
        this.ui.qaContainer.innerHTML = '<div class="empty-state"><p>No questions detected yet</p></div>';
        this.ui.qaCount.textContent = '0';
        this.ui.titleInput.value = 'Team Meeting';
        this.ui.stopBtn.disabled = false;
        this.ui.stopBtn.textContent = 'End Meeting';
        this.ui.startBtn.disabled = false;
        this.ui.startBtn.innerHTML = '<span class="btn-icon">●</span>Start Recording';
        
        // Clear URL
        window.history.pushState({}, '', '/');
        
        // Show setup
        this.showScreen('setup');
    }

    showScreen(screenName) {
        ['setup', 'meeting', 'completion'].forEach(name => {
            const screen = this.ui[name + 'Screen'];
            if (name === screenName) {
                screen.classList.add('active');
            } else {
                screen.classList.remove('active');
            }
        });
    }

    startDurationTimer() {
        this.durationInterval = setInterval(() => {
            this.ui.duration.textContent = this.calculateDuration();
        }, 1000);
    }

    stopDurationTimer() {
        if (this.durationInterval) {
            clearInterval(this.durationInterval);
            this.durationInterval = null;
        }
    }

    calculateDuration() {
        if (!this.startTime) return '00:00:00';
        const diff = Math.floor((new Date() - this.startTime) / 1000);
        const hours = Math.floor(diff / 3600);
        const minutes = Math.floor((diff % 3600) / 60);
        const seconds = diff % 60;
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }

    formatTime(timestamp) {
        if (!timestamp) return '--:--';
        const date = new Date(timestamp * 1000);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async joinExistingMeeting(meetingId) {
        // TODO: Implement joining existing active meeting
        console.log('Joining meeting:', meetingId);
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new MeetingApp();
});