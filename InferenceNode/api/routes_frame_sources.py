"""
Frame Source API Routes
Handles frame source discovery and configuration
"""
from flask import request, jsonify


def register_frame_source_routes(app, node):
    """Register all frame source-related routes"""
    
    @app.route('/api/frame-sources', methods=['GET'])
    def get_frame_sources():
        """Get available frame source types with their metadata"""
        try:
            from frame_source import get_available_sources
            frame_sources = get_available_sources()
            
            # Enhance video_file source with upload capability
            for source in frame_sources:
                if source.get('type') == 'video_file' and 'config_schema' in source:
                    schema = source['config_schema']
                    # Check if it has a fields array
                    if 'fields' in schema and isinstance(schema['fields'], list):
                        # Check if upload_file field doesn't already exist
                        has_upload_field = any(f.get('name') == 'upload_file' for f in schema['fields'])
                        if not has_upload_field:
                            # Insert upload_file field at the beginning
                            upload_field = {
                                'name': 'upload_file',
                                'type': 'file',
                                'label': 'Upload Video File',
                                'description': 'Upload a video file (MP4, AVI, MOV, etc.)',
                                'accept': '.mp4,.avi,.mov,.mkv,.wmv,.flv,.webm,.m4v,.mpg,.mpeg',
                                'upload_endpoint': '/api/media/upload-video',
                                'required': False
                            }
                            schema['fields'].insert(0, upload_field)
                            
                            # Update the source field description to mention upload
                            for field in schema['fields']:
                                if field.get('name') == 'source':
                                    field['description'] = 'Path to the video file (auto-populated after upload, or enter manually)'
                                    field['placeholder'] = 'Enter file path or upload a video above'
            
            return jsonify({
                'status': 'success',
                'frame_sources': frame_sources
            })
            
        except ImportError as e:
            node.logger.warning(f"FrameSource module not available: {str(e)}. Using fallback frame sources.")
            # Provide fallback frame sources
            fallback_sources = [
                {
                    'type': 'webcam',
                    'name': 'Webcam',
                    'description': 'Local webcam or camera device',
                    'icon': 'fas fa-video',
                    'primary': True,
                    'available': True,
                    'config_schema': {
                        'fields': [
                            {'name': 'source', 'type': 'number', 'label': 'Camera Index', 'default': 0, 'required': True},
                            {'name': 'width', 'type': 'number', 'label': 'Width', 'default': 640, 'required': False},
                            {'name': 'height', 'type': 'number', 'label': 'Height', 'default': 480, 'required': False}
                        ]
                    }
                }
            ]
            
            return jsonify({
                'status': 'success',
                'frame_sources': fallback_sources,
                'fallback': True
            })
            
        except Exception as e:
            node.logger.error(f"Get frame sources error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/frame-sources/<source_type>/discover', methods=['GET'])
    def discover_frame_sources(source_type):
        """Discover available devices for a specific frame source type"""
        success = False
        try:
            devices = []
            
            # Try to import and use the frame source module
            try:
                from frame_source import FrameSourceFactory
                
                # # Special handling for different source types
                # if source_type == 'webcam':
                #     devices = self._discover_webcam_devices()
                # elif source_type == 'audio_spectrogram':
                #     devices = self._discover_audio_devices()
                # else:
                #     # Try to create a frame source instance for discovery
                try:
                    frame_source = FrameSourceFactory.create(capture_type=source_type)
                    if hasattr(frame_source, 'discover'):
                        discovered = frame_source.discover()
                        # Ensure the returned data has the expected format
                        if isinstance(discovered, list):
                            devices = discovered
                        else:
                            devices = []
                    elif hasattr(frame_source.__class__, 'discover'):
                        discovered = frame_source.__class__.discover()
                        if isinstance(discovered, list):
                            devices = discovered
                        else:
                            devices = []
                    else:
                        devices = []
                    
                    success = True
                except Exception as inner_e:
                    app.logger.debug(f"Could not create {source_type} frame source for discovery: {str(inner_e)}")
                    devices = []
                
                # app.logger.info(f"Discovered {len(devices)} devices for {source_type}")
                    
            except ImportError:
                # Fallback discovery for basic types
                # if source_type == 'webcam':
                #     devices = self._discover_webcam_devices()
                # elif source_type == 'audio_spectrogram':
                #     devices = self._discover_audio_devices()
                # else:
                devices = []
            
            return jsonify({
                'success': success,
                'devices': devices or [],
                'count': len(devices) if devices else 0,
                'source_type': source_type
            })
            
        except Exception as e:
            app.logger.error(f"Frame source device discovery error for {source_type}: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e),
                'devices': []
            }), 500