"""
Offline Speech-to-Text using Vosk.
Self-hosted, no API keys required.
"""

import os
import json
import wave
import io
from vosk import Model, KaldiRecognizer
import numpy as np

class OfflineTranscriber:
    """
    Offline speech recognition using Vosk.
    Loads model once, processes audio chunks.
    """
    
    def __init__(self, model_path=None):
        self.model_path = model_path or self._get_default_model_path()
        self.model = None
        self._load_model()
    
    def _get_default_model_path(self):
        """Get default model path."""
        # Check common locations
        paths = [
            "models/vosk-model-en-us-0.22",
            "/tmp/models/vosk-model-en-us-0.22",
            os.path.join(os.path.dirname(__file__), "../../models/vosk-model-en-us-0.22")
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return paths[0]  # Default fallback
    
    def _load_model(self):
        """Load Vosk model."""
        try:
            if not os.path.exists(self.model_path):
                print(f"Model not found at {self.model_path}, downloading...")
                self._download_model()
            
            self.model = Model(self.model_path)
            print("Vosk model loaded successfully")
        except Exception as e:
            print(f"Error loading model: {e}")
            raise
    
    def _download_model(self):
        """
        Download model if not present.
        In production, model should be included in deployment package.
        """
        import urllib.request
        import zipfile
        
        model_url = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
        zip_path = "/tmp/vosk-model.zip"
        
        print(f"Downloading model from {model_url}...")
        urllib.request.urlretrieve(model_url, zip_path)
        
        print("Extracting model...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("/tmp/models/")
        
        os.remove(zip_path)
        self.model_path = "/tmp/models/vosk-model-en-us-0.22"
    
    def transcribe(self, audio_data, sample_rate=16000):
        """
        Transcribe audio numpy array to text.
        Returns transcribed string.
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")
        
        # Convert numpy array to WAV format bytes
        wav_bytes = self._numpy_to_wav(audio_data, sample_rate)
        
        # Process with Vosk
        recognizer = KaldiRecognizer(self.model, sample_rate)
        recognizer.SetWords(True)
        
        results = []
        
        # Process in chunks to simulate streaming
        chunk_size = 4096
        offset = 44  # Skip WAV header
        
        while offset < len(wav_bytes):
            chunk = wav_bytes[offset:offset + chunk_size]
            if recognizer.AcceptWaveform(chunk):
                result = json.loads(recognizer.Result())
                if result.get('text'):
                    results.append(result['text'])
            offset += chunk_size
        
        # Get final result
        final_result = json.loads(recognizer.FinalResult())
        if final_result.get('text'):
            results.append(final_result['text'])
        
        return ' '.join(results).strip()
    
    def _numpy_to_wav(self, audio_data, sample_rate):
        """Convert numpy array to WAV bytes."""
        # Ensure int16 format
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        # Create WAV file in memory
        byte_io = io.BytesIO()
        
        with wave.open(byte_io, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_int16.tobytes())
        
        return byte_io.getvalue()
    
    def transcribe_stream(self, audio_generator):
        """
        Stream transcription for real-time processing.
        Yields partial results.
        """
        recognizer = KaldiRecognizer(self.model, 16000)
        recognizer.SetWords(True)
        
        for audio_chunk in audio_generator:
            wav_bytes = self._numpy_to_wav(audio_chunk, 16000)
            
            if recognizer.AcceptWaveform(wav_bytes[44:]):  # Skip header after first
                result = json.loads(recognizer.Result())
                if result.get('text'):
                    yield {
                        'type': 'partial',
                        'text': result['text'],
                        'confidence': result.get('confidence', 0)
                    }
        
        final = json.loads(recognizer.FinalResult())
        if final.get('text'):
            yield {
                'type': 'final',
                'text': final['text'],
                'confidence': final.get('confidence', 0)
            }