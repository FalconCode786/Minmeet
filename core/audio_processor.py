"""
Audio Buffer and Preprocessing Module.
Handles audio chunking, buffering, and format conversion.
"""

import numpy as np
import librosa
import io
from pathlib import Path

class AudioBuffer:
    """
    Manages audio buffering for streaming transcription.
    Handles overlap to ensure no audio is lost between chunks.
    """
    
    def __init__(self, sample_rate=16000, chunk_duration=5.0, overlap=0.5):
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.overlap = overlap
        self.buffer = np.array([], dtype=np.float32)
        self.chunk_samples = int(chunk_duration * sample_rate)
        self.overlap_samples = int(overlap * sample_rate)
    
    def add_audio(self, audio_data):
        """
        Add new audio data to buffer.
        Returns complete chunks when available.
        """
        self.buffer = np.concatenate([self.buffer, audio_data])
        
        chunks = []
        while len(self.buffer) >= self.chunk_samples:
            chunk = self.buffer[:self.chunk_samples]
            chunks.append(chunk)
            # Keep overlap for continuity
            self.buffer = self.buffer[self.chunk_samples - self.overlap_samples:]
        
        return chunks
    
    def flush(self):
        """Return remaining buffer content."""
        remaining = self.buffer.copy()
        self.buffer = np.array([], dtype=np.float32)
        return remaining if len(remaining) > self.sample_rate * 0.5 else None
    
    @staticmethod
    def convert_to_wav(webm_data, target_sr=16000):
        """
        Convert WebM/OGG audio from browser to WAV format.
        Uses librosa for robust format handling.
        """
        try:
            # Load audio from bytes
            audio, sr = librosa.load(
                io.BytesIO(webm_data),
                sr=target_sr,
                mono=True,
                dtype=np.float32
            )
            return audio, target_sr
        except Exception as e:
            print(f"Audio conversion error: {e}")
            return None, None
    
    @staticmethod
    def normalize_audio(audio):
        """Normalize audio to [-1, 1] range."""
        if audio is None or len(audio) == 0:
            return audio
        
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            return audio / max_val
        return audio
    
    @staticmethod
    def remove_silence(audio, threshold=0.01, min_length=0.5):
        """
        Remove silence from audio to improve processing efficiency.
        Returns non-silent segments.
        """
        # Calculate energy
        energy = np.abs(audio)
        
        # Find non-silent regions
        non_silent = energy > threshold
        
        # Find segments
        segments = []
        start = None
        
        for i, is_active in enumerate(non_silent):
            if is_active and start is None:
                start = i
            elif not is_active and start is not None:
                if (i - start) / 16000 >= min_length:  # min_length in seconds
                    segments.append(audio[start:i])
                start = None
        
        # Handle trailing segment
        if start is not None and (len(audio) - start) / 16000 >= min_length:
            segments.append(audio[start:])
        
        if segments:
            return np.concatenate(segments)
        return np.array([], dtype=np.float32)