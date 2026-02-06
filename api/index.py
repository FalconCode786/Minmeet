"""
Vercel Serverless Function Entry Point.
Adapts Flask app for Vercel's serverless runtime.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app

# Vercel serverless handler
def handler(request, context):
    """
    Vercel serverless function handler.
    Wraps Flask WSGI application.
    """
    from werkzeug.wrappers import Request as WerkzeugRequest
    from werkzeug.wrappers import Response as WerkzeugResponse
    from io import BytesIO
    
    # Convert Vercel request to WSGI environ
    environ = request.environ
    
    # Handle body
    if request.body:
        environ['wsgi.input'] = BytesIO(request.body)
    else:
        environ['wsgi.input'] = BytesIO()
    
    environ['CONTENT_LENGTH'] = str(len(request.body) if request.body else 0)
    
    # Create response buffer
    response_buffer = []
    headers_set = []
    headers_sent = []
    
    def start_response(status, headers, exc_info=None):
        headers_set[:] = [status, headers]
        return response_buffer.append
    
    # Execute Flask app
    response_body = flask_app(environ, start_response)
    
    # Collect response
    body = b''.join(response_body)
    
    # Parse status
    status_code = int(headers_set[0].split(' ')[0])
    
    # Convert headers
    response_headers = dict(headers_set[1])
    
    return {
        'statusCode': status_code,
        'headers': response_headers,
        'body': body.decode('utf-8') if isinstance(body, bytes) else body
    }