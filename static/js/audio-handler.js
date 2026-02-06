/**
 * Audio Handler Module
 * Manages browser audio capture, visualization, and chunk transmission.
 * No external dependencies - uses native Web APIs.
 */

class AudioHandler {
    constructor() {
        this.mediaRecorder = null;
        this.audioContext = null;
        this.analyser = null;
        this.source = null;
        this.stream = null;
        this.chunks = [];
        this.isRecording = false;
        this.chunkInterval = 5000; // 5 seconds per chunk
        this.chunkTimer = null;
        this.onChunkReady = null;
        this.onVisualizerData = null;
        this.visualizerInterval = null;
    }

    async initialize() {
        try {
            // Request microphone access
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 16000
                }
            });

            // Setup audio context for visualization
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            this.analyser.smoothingTimeConstant = 0.8;

            this.source = this.audioContext.createMediaStreamSource(this.stream);
            this.source.connect(this.analyser);

            // Setup media recorder with specific mime type
            const mimeType = this._getSupportedMimeType();
            this.mediaRecorder = new MediaRecorder(this.stream, {
                mimeType: mimeType,
                audioBitsPerSecond: 128000
            });

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.chunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                this._sendChunk();
            };

            return true;
        } catch (error) {
            console.error('Audio initialization failed:', error);
            throw new Error(`Microphone access denied or not available: ${error.message}`);
        }
    }

    _getSupportedMimeType() {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/ogg',
            'audio/mp4'
        ];
        
        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }
        return 'audio/webm'; // Fallback
    }

    startRecording(onChunkReady) {
        if (!this.mediaRecorder) {
            throw new Error('Audio not initialized. Call initialize() first.');
        }

        this.onChunkReady = onChunkReady;
        this.isRecording = true;
        this.chunks = [];

        // Start recording
        this.mediaRecorder.start();
        
        // Setup periodic chunk capture
        this.chunkTimer = setInterval(() => {
            if (this.mediaRecorder.state === 'recording') {
                this.mediaRecorder.requestData();
                setTimeout(() => this._sendChunk(), 100); // Small delay to ensure data is available
            }
        }, this.chunkInterval);

        // Start visualization
        this._startVisualization();

        return true;
    }

    stopRecording() {
        this.isRecording = false;

        if (this.chunkTimer) {
            clearInterval(this.chunkTimer);
            this.chunkTimer = null;
        }

        if (this.visualizerInterval) {
            clearInterval(this.visualizerInterval);
            this.visualizerInterval = null;
        }

        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }

        // Stop all tracks
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
        }

        if (this.audioContext) {
            this.audioContext.close();
        }

        // Send any remaining chunks
        if (this.chunks.length > 0) {
            this._sendChunk(true);
        }
    }

    _sendChunk(isFinal = false) {
        if (this.chunks.length === 0) return;

        const blob = new Blob(this.chunks, { type: this.mediaRecorder.mimeType });
        this.chunks = []; // Clear chunks

        if (this.onChunkReady) {
            this.onChunkReady(blob, isFinal);
        }
    }

    _startVisualization() {
        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        this.visualizerInterval = setInterval(() => {
            this.analyser.getByteFrequencyData(dataArray);
            
            // Calculate average volume for simple visualization
            let sum = 0;
            for (let i = 0; i < bufferLength; i++) {
                sum += dataArray[i];
            }
            const average = sum / bufferLength;

            if (this.onVisualizerData) {
                this.onVisualizerData(dataArray, average);
            }
        }, 1000 / 30); // 30fps
    }

    // Static helper to check permissions
    static async checkPermissions() {
        try {
            const result = await navigator.permissions.query({ name: 'microphone' });
            return result.state;
        } catch (e) {
            return 'prompt'; // Default to prompt if API not supported
        }
    }
}