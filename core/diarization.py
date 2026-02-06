"""
Speaker Diarization using clustering of voice features.
Offline processing, no enrollment required.
"""

import numpy as np
import librosa
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import StandardScaler
import hashlib
import json
import sqlite3

class SpeakerDiarizer:
    """
    Identifies unique speakers using voice embeddings and clustering.
    Maintains speaker consistency across chunks.
    """
    
    def __init__(self, n_clusters=None, threshold=0.85):
        self.n_clusters = n_clusters
        self.threshold = threshold
        self.scaler = StandardScaler()
        self.speaker_embeddings = {}  # meeting_id -> {speaker_id: embedding}
    
    def extract_features(self, audio, sr=16000):
        """
        Extract voice features for speaker identification.
        Uses MFCCs, spectral features, and prosody.
        """
        # Ensure minimum length
        if len(audio) < sr * 0.5:  # At least 0.5 seconds
            return None
        
        features = []
        
        # MFCCs (Mel-frequency cepstral coefficients)
        mfccs = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=20)
        mfcc_means = np.mean(mfccs, axis=1)
        mfcc_vars = np.var(mfccs, axis=1)
        features.extend(mfcc_means)
        features.extend(mfcc_vars)
        
        # Spectral features
        spectral_centroids = librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
        spectral_rolloff = librosa.feature.spectral_rolloff(y=audio, sr=sr)[0]
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=audio, sr=sr)[0]
        
        features.append(np.mean(spectral_centroids))
        features.append(np.var(spectral_centroids))
        features.append(np.mean(spectral_rolloff))
        features.append(np.var(spectral_rolloff))
        features.append(np.mean(spectral_bandwidth))
        features.append(np.var(spectral_bandwidth))
        
        # Zero crossing rate (voice activity)
        zcr = librosa.feature.zero_crossing_rate(audio)[0]
        features.append(np.mean(zcr))
        features.append(np.var(zcr))
        
        # RMS energy (loudness)
        rms = librosa.feature.rms(y=audio)[0]
        features.append(np.mean(rms))
        features.append(np.var(rms))
        
        # Pitch (fundamental frequency)
        pitches, magnitudes = librosa.piptrack(y=audio, sr=sr)
        pitch_mean = np.mean(pitches[magnitudes > np.max(magnitudes) * 0.5])
        if not np.isnan(pitch_mean):
            features.append(pitch_mean)
        else:
            features.append(0)
        
        return np.array(features)
    
    def identify_speaker(self, audio, sr, meeting_id):
        """
        Identify speaker for audio chunk.
        Returns consistent speaker ID for meeting.
        """
        features = self.extract_features(audio, sr)
        if features is None:
            return "unknown"
        
        # Normalize features
        features = features.reshape(1, -1)
        
        # Get existing speakers for this meeting
        if meeting_id not in self.speaker_embeddings:
            self.speaker_embeddings[meeting_id] = {}
        
        existing_speakers = self.speaker_embeddings[meeting_id]
        
        if not existing_speakers:
            # First speaker
            speaker_id = self._generate_speaker_id(features)
            self.speaker_embeddings[meeting_id][speaker_id] = features
            return speaker_id
        
        # Compare with existing speakers
        best_match = None
        best_score = -1
        
        for speaker_id, embedding in existing_speakers.items():
            similarity = self._cosine_similarity(features, embedding)
            if similarity > best_score:
                best_score = similarity
                best_match = speaker_id
        
        # If similar enough, return existing speaker
        if best_score > self.threshold:
            # Update embedding with moving average
            self.speaker_embeddings[meeting_id][best_match] = (
                0.8 * self.speaker_embeddings[meeting_id][best_match] + 
                0.2 * features
            )
            return best_match
        
        # New speaker
        new_speaker_id = self._generate_speaker_id(features)
        self.speaker_embeddings[meeting_id][new_speaker_id] = features
        return new_speaker_id
    
    def _cosine_similarity(self, a, b):
        """Calculate cosine similarity between vectors."""
        dot = np.dot(a.flatten(), b.flatten())
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        return dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0
    
    def _generate_speaker_id(self, features):
        """Generate unique speaker ID from feature hash."""
        feature_str = np.array2string(features, precision=2)
        return hashlib.md5(feature_str.encode()).hexdigest()[:12]
    
    def cluster_speakers(self, audio_segments, sr=16000):
        """
        Batch clustering for offline processing.
        Used for post-processing to improve accuracy.
        """
        embeddings = []
        valid_segments = []
        
        for segment in audio_segments:
            feat = self.extract_features(segment, sr)
            if feat is not None:
                embeddings.append(feat)
                valid_segments.append(segment)
        
        if len(embeddings) < 2:
            return [0] * len(audio_segments)
        
        embeddings = np.array(embeddings)
        embeddings = self.scaler.fit_transform(embeddings)
        
        # Determine optimal clusters (up to 10 speakers)
        n_clusters = min(10, len(embeddings) // 3) if self.n_clusters is None else self.n_clusters
        
        clustering = AgglomerativeClustering(
            n_clusters=n_clusters,
            metric='cosine',
            linkage='average'
        )
        
        labels = clustering.fit_predict(embeddings)
        return labels