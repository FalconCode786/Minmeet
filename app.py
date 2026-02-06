"""
Flask Application Factory for Meeting Minutes System.
Designed for Vercel serverless deployment with stateless architecture.
"""

import os
import uuid
import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_file
from flask import stream_with_context
import threading
import queue

# Core modules
from core.audio_processor import AudioBuffer
from core.transcriber import OfflineTranscriber
from core.diarization import SpeakerDiarizer
from core.qa_engine import QAProcessor
from core.minutes_builder import MinutesBuilder
from core.pdf_generator import PDFGenerator

# Configuration
DATABASE_PATH = os.environ.get('DATABASE_PATH', '/tmp/meetings.db')
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', '/tmp/audio_chunks')
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max audio chunk

def get_db_connection():
    """Create database connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize SQLite database with required tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Meetings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT 'Untitled Meeting',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            participant_count INTEGER DEFAULT 0,
            transcript TEXT DEFAULT '[]',
            qa_pairs TEXT DEFAULT '[]',
            decisions TEXT DEFAULT '[]',
            action_items TEXT DEFAULT '[]',
            pdf_path TEXT
        )
    ''')
    
    # Audio chunks table (temporary storage)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audio_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT,
            chunk_data BLOB,
            timestamp REAL,
            processed BOOLEAN DEFAULT 0,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        )
    ''')
    
    # Speakers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS speakers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT,
            speaker_id TEXT,
            voice_fingerprint TEXT,
            display_name TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def create_app():
    """Application factory pattern for Flask."""
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
    
    # Ensure temp directories exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Initialize core components (lazy loading for serverless)
    transcriber = None
    diarizer = None
    
    def get_transcriber():
        nonlocal transcriber
        if transcriber is None:
            transcriber = OfflineTranscriber()
        return transcriber
    
    def get_diarizer():
        nonlocal diarizer
        if diarizer is None:
            diarizer = SpeakerDiarizer()
        return diarizer
    
    @app.route('/api/health')
    def health_check():
        """Health check endpoint."""
        return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})
    
    @app.route('/api/meetings/start', methods=['POST'])
    def start_meeting():
        """
        Start a new meeting session.
        Returns meeting ID for subsequent requests.
        """
        data = request.get_json() or {}
        meeting_id = str(uuid.uuid4())
        title = data.get('title', f'Meeting {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO meetings (id, title, status) VALUES (?, ?, ?)',
            (meeting_id, title, 'active')
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            "meeting_id": meeting_id,
            "title": title,
            "status": "active",
            "started_at": datetime.now().isoformat()
        })
    
    @app.route('/api/meetings/<meeting_id>/audio', methods=['POST'])
    def receive_audio(meeting_id):
        """
        Receive audio chunk from frontend.
        Chunk is queued for processing (async in serverless via separate processing).
        """
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400
        
        audio_file = request.files['audio']
        timestamp = float(request.form.get('timestamp', datetime.now().timestamp()))
        
        # Save chunk temporarily
        chunk_path = os.path.join(UPLOAD_FOLDER, f"{meeting_id}_{timestamp}.webm")
        audio_file.save(chunk_path)
        
        # Store in database for processing
        conn = get_db_connection()
        with open(chunk_path, 'rb') as f:
            chunk_data = f.read()
        
        conn.execute(
            'INSERT INTO audio_chunks (meeting_id, chunk_data, timestamp) VALUES (?, ?, ?)',
            (meeting_id, chunk_data, timestamp)
        )
        conn.commit()
        conn.close()
        
        # Trigger immediate processing (Vercel serverless - process synchronously)
        # In production, this would be a background job
        process_audio_chunk(meeting_id, chunk_path, timestamp)
        
        return jsonify({
            "status": "received",
            "timestamp": timestamp,
            "meeting_id": meeting_id
        })
    
    def process_audio_chunk(meeting_id, chunk_path, timestamp):
        """
        Process single audio chunk: transcribe, diarize, detect Q&A.
        Stateless processing suitable for serverless.
        """
        try:
            # Initialize processors
            transcriber = get_transcriber()
            diarizer = get_diarizer()
            qa_engine = QAProcessor()
            
            # Load audio
            import librosa
            audio, sr = librosa.load(chunk_path, sr=16000, mono=True)
            
            # Speaker diarization
            speaker_id = diarizer.identify_speaker(audio, sr, meeting_id)
            
            # Transcription
            transcription = transcriber.transcribe(audio, sr)
            
            if not transcription or not transcription.strip():
                return
            
            # Detect if question
            is_question = qa_engine.is_question(transcription)
            
            # Get or create speaker name
            conn = get_db_connection()
            speaker_row = conn.execute(
                'SELECT display_name FROM speakers WHERE meeting_id = ? AND speaker_id = ?',
                (meeting_id, speaker_id)
            ).fetchone()
            
            if speaker_row:
                speaker_name = speaker_row['display_name']
            else:
                # New speaker
                speaker_num = conn.execute(
                    'SELECT COUNT(*) FROM speakers WHERE meeting_id = ?',
                    (meeting_id,)
                ).fetchone()[0] + 1
                speaker_name = f"Participant {speaker_num}"
                
                conn.execute(
                    'INSERT INTO speakers (meeting_id, speaker_id, display_name) VALUES (?, ?, ?)',
                    (meeting_id, speaker_id, speaker_name)
                )
                
                # Update participant count
                conn.execute(
                    'UPDATE meetings SET participant_count = ? WHERE id = ?',
                    (speaker_num, meeting_id)
                )
            
            # Get current transcript
            meeting = conn.execute(
                'SELECT transcript, qa_pairs FROM meetings WHERE id = ?',
                (meeting_id,)
            ).fetchone()
            
            transcript = json.loads(meeting['transcript'])
            qa_pairs = json.loads(meeting['qa_pairs'])
            
            # Add to transcript
            entry = {
                "timestamp": timestamp,
                "speaker": speaker_name,
                "text": transcription,
                "is_question": is_question,
                "id": str(uuid.uuid4())
            }
            transcript.append(entry)
            
            # Q&A processing
            if is_question:
                qa_pairs.append({
                    "question": entry,
                    "answers": [],
                    "resolved": False
                })
            else:
                # Link to most recent unresolved question
                for qa in reversed(qa_pairs):
                    if not qa.get('resolved', False):
                        qa['answers'].append(entry)
                        # Auto-resolve if statement looks conclusive
                        if qa_engine.is_conclusive_answer(transcription):
                            qa['resolved'] = True
                        break
            
            # Update database
            conn.execute(
                'UPDATE meetings SET transcript = ?, qa_pairs = ? WHERE id = ?',
                (json.dumps(transcript), json.dumps(qa_pairs), meeting_id)
            )
            
            # Mark chunk as processed
            conn.execute(
                'UPDATE audio_chunks SET processed = 1 WHERE meeting_id = ? AND timestamp = ?',
                (meeting_id, timestamp)
            )
            
            conn.commit()
            conn.close()
            
            # Cleanup temp file
            os.remove(chunk_path)
            
        except Exception as e:
            print(f"Error processing chunk: {e}")
            # Ensure cleanup
            if os.path.exists(chunk_path):
                os.remove(chunk_path)
    
    @app.route('/api/meetings/<meeting_id>/stream')
    def stream_minutes(meeting_id):
        """
        Server-Sent Events endpoint for real-time updates.
        Sends incremental updates to frontend.
        """
        def event_stream():
            last_transcript_len = 0
            last_qa_len = 0
            
            while True:
                try:
                    conn = get_db_connection()
                    meeting = conn.execute(
                        'SELECT transcript, qa_pairs, status, participant_count FROM meetings WHERE id = ?',
                        (meeting_id,)
                    ).fetchone()
                    conn.close()
                    
                    if not meeting:
                        yield f"data: {json.dumps({'error': 'Meeting not found'})}\n\n"
                        break
                    
                    transcript = json.loads(meeting['transcript'])
                    qa_pairs = json.loads(meeting['qa_pairs'])
                    
                    # Only send if new content
                    if len(transcript) > last_transcript_len or len(qa_pairs) > last_qa_len:
                        new_entries = transcript[last_transcript_len:]
                        new_qa = qa_pairs[last_qa_len:]
                        
                        data = {
                            "transcript": new_entries,
                            "qa_pairs": new_qa,
                            "total_speakers": meeting['participant_count'],
                            "status": meeting['status'],
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        yield f"data: {json.dumps(data)}\n\n"
                        
                        last_transcript_len = len(transcript)
                        last_qa_len = len(qa_pairs)
                    
                    # If meeting ended, send final update and close
                    if meeting['status'] == 'completed':
                        yield f"data: {json.dumps({'status': 'completed', 'redirect': f'/api/meetings/{meeting_id}/pdf'})}\n\n"
                        break
                    
                    # Sleep to prevent tight loop (serverless-friendly)
                    import time
                    time.sleep(1)
                    
                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    break
        
        return Response(
            stream_with_context(event_stream()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
    
    @app.route('/api/meetings/<meeting_id>/minutes', methods=['GET'])
    def get_minutes(meeting_id):
        """
        REST API fallback for polling (if SSE not supported).
        Returns current state of minutes.
        """
        conn = get_db_connection()
        meeting = conn.execute(
            'SELECT * FROM meetings WHERE id = ?',
            (meeting_id,)
        ).fetchone()
        conn.close()
        
        if not meeting:
            return jsonify({"error": "Meeting not found"}), 404
        
        minutes_builder = MinutesBuilder()
        structured = minutes_builder.build_minutes(
            json.loads(meeting['transcript']),
            json.loads(meeting['qa_pairs']),
            json.loads(meeting.get('decisions', '[]')),
            json.loads(meeting.get('action_items', '[]'))
        )
        
        return jsonify({
            "meeting_id": meeting_id,
            "title": meeting['title'],
            "status": meeting['status'],
            "participants": meeting['participant_count'],
            "started_at": meeting['created_at'],
            "ended_at": meeting['ended_at'],
            "minutes": structured
        })
    
    @app.route('/api/meetings/<meeting_id>/stop', methods=['POST'])
    def stop_meeting(meeting_id):
        """
        Stop meeting and trigger PDF generation.
        """
        conn = get_db_connection()
        meeting = conn.execute(
            'SELECT * FROM meetings WHERE id = ?',
            (meeting_id,)
        ).fetchone()
        
        if not meeting:
            conn.close()
            return jsonify({"error": "Meeting not found"}), 404
        
        # Generate final minutes structure
        minutes_builder = MinutesBuilder()
        structured_minutes = minutes_builder.build_minutes(
            json.loads(meeting['transcript']),
            json.loads(meeting['qa_pairs']),
            [],  # Decisions extracted by builder
            []   # Action items extracted by builder
        )
        
        # Update meeting status
        conn.execute(
            'UPDATE meetings SET status = ?, ended_at = ?, decisions = ?, action_items = ? WHERE id = ?',
            (
                'completed',
                datetime.now().isoformat(),
                json.dumps(structured_minutes.get('decisions', [])),
                json.dumps(structured_minutes.get('action_items', [])),
                meeting_id
            )
        )
        conn.commit()
        
        # Generate PDF
        pdf_gen = PDFGenerator()
        pdf_path = os.path.join('/tmp', f'meeting_{meeting_id}.pdf')
        pdf_gen.generate(
            meeting_title=meeting['title'],
            meeting_date=meeting['created_at'],
            participants=[f"Participant {i+1}" for i in range(meeting['participant_count'])],
            transcript=json.loads(meeting['transcript']),
            qa_pairs=json.loads(meeting['qa_pairs']),
            decisions=structured_minutes.get('decisions', []),
            action_items=structured_minutes.get('action_items', []),
            output_path=pdf_path
        )
        
        conn.execute(
            'UPDATE meetings SET pdf_path = ? WHERE id = ?',
            (pdf_path, meeting_id)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "completed",
            "meeting_id": meeting_id,
            "pdf_url": f"/api/meetings/{meeting_id}/pdf",
            "duration": "calculated"
        })
    
    @app.route('/api/meetings/<meeting_id>/pdf', methods=['GET'])
    def download_pdf(meeting_id):
        """
        Download generated PDF.
        """
        conn = get_db_connection()
        meeting = conn.execute(
            'SELECT pdf_path, title FROM meetings WHERE id = ?',
            (meeting_id,)
        ).fetchone()
        conn.close()
        
        if not meeting or not meeting['pdf_path']:
            return jsonify({"error": "PDF not found"}), 404
        
        if not os.path.exists(meeting['pdf_path']):
            return jsonify({"error": "PDF file missing"}), 404
        
        return send_file(
            meeting['pdf_path'],
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{meeting['title'].replace(' ', '_')}_Minutes.pdf"
        )
    
    return app

# Vercel handler
app = create_app()