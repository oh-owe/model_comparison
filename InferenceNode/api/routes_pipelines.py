"""
Pipeline management API routes for InferenceNode
Handles pipeline CRUD operations, control, streaming, and import/export
"""

from flask import jsonify, request, Response
import os
import time
import cv2
import tempfile
import zipfile
import json
import shutil
from datetime import datetime

try:
    from ..settings_manager import save_settings
except ImportError:
    from InferenceNode.settings_manager import save_settings


def register_pipeline_routes(app, node):
    """Register all pipeline-related routes with the Flask app"""
    
    @app.route('/api/pipeline/create', methods=['POST'])
    def create_pipeline():
        """Create a new inference pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            config = request.get_json()
            
            # Validate required fields
            required_fields = ['name', 'frame_source', 'model', 'destinations']
            for field in required_fields:
                if field not in config:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
            
            # Format device string for the specific inference engine
            if 'model' in config and 'device' in config['model'] and 'engine_type' in config['model']:
                original_device = config['model']['device']
                engine_type = config['model']['engine_type']
                
                # Use hardware detector to format device for the specific engine
                formatted_device = node.hardware_detector.format_for(engine_type, original_device)
                config['model']['device'] = formatted_device
                
                node.logger.info(f"Device '{original_device}' formatted to '{formatted_device}' for engine '{engine_type}'")
            
            # Create pipeline
            pipeline_id = node.pipeline_manager.create_pipeline(config)
            
            # Update node info with new pipeline information
            node._update_node_info_with_pipelines()
            
            node.logger.info(f"Pipeline created: {config['name']} ({pipeline_id})")
            
            return jsonify({
                'pipeline_id': pipeline_id,
                'status': 'created',
                'message': f'Pipeline "{config["name"]}" created successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Create pipeline error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipelines/metrics', methods=['GET'])
    def get_pipeline_metrics():
        """Get only pipeline metrics (lighter endpoint for frequent polling)"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
            
            # Get only the metrics without full pipeline data
            stats = node.pipeline_manager.get_pipeline_stats()
            
            # Get metrics for running pipelines only
            running_metrics = {}
            for pipeline_id, pipeline_info in node.pipeline_manager.active_pipelines.items():
                if 'pipeline_instance' in pipeline_info:
                    pipeline_instance = pipeline_info['pipeline_instance']
                    if hasattr(pipeline_instance, 'get_metrics'):
                        try:
                            metrics = pipeline_instance.get_metrics()
                            running_metrics[pipeline_id] = {
                                'fps': round(metrics.get('fps', 0), 1),
                                'frame_count': metrics.get('frame_count', 0),
                                'elapsed_time': round(metrics.get('elapsed_time', 0), 1),
                                'latency_ms': round(metrics.get('latency_ms', 0), 1),
                                'uptime': metrics.get('uptime', '0s')
                            }
                        except Exception as e:
                            print(f"Error getting metrics for pipeline {pipeline_id}: {e}")
            
            return jsonify({
                'stats': stats,
                'running_pipelines': running_metrics
            })
            
        except Exception as e:
            node.logger.error(f"Get pipeline metrics error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipelines', methods=['GET'])
    def list_pipelines():
        """List all pipelines"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            pipelines = node.pipeline_manager.list_pipelines()
            stats = node.pipeline_manager.get_pipeline_stats()
            
            return jsonify({
                'pipelines': list(pipelines.values()),
                'stats': stats
            })
            
        except Exception as e:
            node.logger.error(f"List pipelines error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipelines/summary', methods=['GET'])
    def get_pipeline_summary():
        """Get pipeline summary for discovery service"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            summary = node.pipeline_manager.get_pipeline_summary()
            return jsonify(summary)
            
        except Exception as e:
            node.logger.error(f"Get pipeline summary error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>', methods=['GET'])
    def get_pipeline(pipeline_id):
        """Get pipeline configuration"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            pipeline = node.pipeline_manager.get_pipeline(pipeline_id)
            if not pipeline:
                return jsonify({'error': 'Pipeline not found'}), 404
            
            return jsonify(pipeline)
            
        except Exception as e:
            node.logger.error(f"Get pipeline error: {str(e)}")
            return jsonify({'error': str(e)}), 500
        
    @app.route('/api/pipeline/<pipeline_id>/fullstatus', methods=['GET'])
    def get_pipeline_full_status(pipeline_id):
        """Get the full status of the pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503

            status = node.pipeline_manager.get_pipeline_status(pipeline_id)
            if not status:
                return jsonify({'error': 'Pipeline not found'}), 404

            return jsonify(status)

        except Exception as e:
            node.logger.error(f"Get pipeline status error: {str(e)}")
            return jsonify({'error': str(e)}), 500
        
    @app.route('/api/pipeline/<pipeline_id>', methods=['DELETE'])
    def delete_pipeline(pipeline_id):
        """Delete a pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            success = node.pipeline_manager.delete_pipeline(pipeline_id)
            if not success:
                return jsonify({'error': 'Pipeline not found'}), 404
            
            # Update node info after pipeline deletion
            node._update_node_info_with_pipelines()
            
            return jsonify({
                'status': 'deleted',
                'pipeline_id': pipeline_id,
                'message': 'Pipeline deleted successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Delete pipeline error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>', methods=['PUT'])
    def update_pipeline(pipeline_id):
        """Update an existing pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            
            # Check if pipeline exists
            pipeline = node.pipeline_manager.get_pipeline(pipeline_id)
            if not pipeline:
                return jsonify({'error': 'Pipeline not found'}), 404
            
            # Check if pipeline is running
            if pipeline.get('status') == 'running':
                return jsonify({'error': 'Cannot update a running pipeline. Please stop it first.'}), 400
            
            # Format device string for the specific inference engine if present
            if 'model' in data and 'device' in data['model'] and 'engine_type' in data['model']:
                original_device = data['model']['device']
                engine_type = data['model']['engine_type']
                
                # Use hardware detector to format device for the specific engine
                formatted_device = node.hardware_detector.format_for(engine_type, original_device)
                data['model']['device'] = formatted_device
                
                node.logger.info(f"Device '{original_device}' formatted to '{formatted_device}' for engine '{engine_type}' (update)")
            
            # Update the pipeline
            success = node.pipeline_manager.update_pipeline(pipeline_id, data)
            if not success:
                return jsonify({'error': 'Failed to update pipeline'}), 500
            
            node.logger.info(f"Pipeline updated: {data.get('name', 'Unknown')} ({pipeline_id})")
            
            return jsonify({
                'status': 'updated',
                'pipeline_id': pipeline_id,
                'message': 'Pipeline updated successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Update pipeline error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/start', methods=['POST'])
    def start_pipeline(pipeline_id):
        """Start a pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            # Log the start attempt
            node.logger.info(f"Attempting to start pipeline: {pipeline_id}")
            
            success = node.pipeline_manager.start_pipeline(
                pipeline_id, 
                node.model_repo, 
                node.result_publisher
            )
            
            if not success:
                error_msg = f'Failed to start pipeline {pipeline_id} - pipeline may be already running, not found, or failed to initialize'
                node.logger.error(error_msg)
                return jsonify({'error': error_msg}), 400
            
            # Update node info with pipeline status change
            node._update_node_info_with_pipelines()
            
            node.logger.info(f"Pipeline started successfully: {pipeline_id}")
            
            return jsonify({
                'status': 'started',
                'pipeline_id': pipeline_id,
                'message': 'Pipeline started successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Start pipeline error for {pipeline_id}: {str(e)}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/stop', methods=['POST'])
    def stop_pipeline(pipeline_id):
        """Stop a pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            success = node.pipeline_manager.stop_pipeline(pipeline_id)
            if not success:
                return jsonify({'error': 'Pipeline not found or not running'}), 400
            
            # Update node info with pipeline status change
            node._update_node_info_with_pipelines()
            
            node.logger.info(f"Pipeline stopped: {pipeline_id}")
            
            return jsonify({
                'status': 'stopped',
                'pipeline_id': pipeline_id,
                'message': 'Pipeline stopped successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Stop pipeline error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/inference/enable', methods=['POST'])
    def enable_pipeline_inference(pipeline_id):
        """Enable inference for a pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            success = node.pipeline_manager.enable_pipeline_inference(pipeline_id)
            if not success:
                return jsonify({'error': 'Pipeline not found'}), 404
            
            node.logger.info(f"Pipeline inference enabled: {pipeline_id}")
            
            return jsonify({
                'status': 'inference_enabled',
                'pipeline_id': pipeline_id,
                'message': 'Inference enabled successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Enable pipeline inference error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/inference/disable', methods=['POST'])
    def disable_pipeline_inference(pipeline_id):
        """Disable inference for a pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            success = node.pipeline_manager.disable_pipeline_inference(pipeline_id)
            if not success:
                return jsonify({'error': 'Pipeline not found'}), 404
            
            node.logger.info(f"Pipeline inference disabled: {pipeline_id}")
            
            return jsonify({
                'status': 'inference_disabled',
                'pipeline_id': pipeline_id,
                'message': 'Inference disabled successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Disable pipeline inference error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/publisher/<publisher_id>/enable', methods=['POST'])
    def enable_pipeline_publisher(pipeline_id, publisher_id):
        """Enable a specific publisher for a pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            success = node.pipeline_manager.enable_pipeline_publisher(pipeline_id, publisher_id)
            if not success:
                return jsonify({'error': 'Pipeline or publisher not found'}), 404
            
            node.logger.info(f"Pipeline publisher enabled: {pipeline_id}/{publisher_id}")
            
            return jsonify({
                'status': 'publisher_enabled',
                'pipeline_id': pipeline_id,
                'publisher_id': publisher_id,
                'message': 'Publisher enabled successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Enable pipeline publisher error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/publisher/<publisher_id>/disable', methods=['POST'])
    def disable_pipeline_publisher(pipeline_id, publisher_id):
        """Disable a specific publisher for a pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            success = node.pipeline_manager.disable_pipeline_publisher(pipeline_id, publisher_id)
            if not success:
                return jsonify({'error': 'Pipeline or publisher not found'}), 404
            
            node.logger.info(f"Pipeline publisher disabled: {pipeline_id}/{publisher_id}")
            
            return jsonify({
                'status': 'publisher_disabled',
                'pipeline_id': pipeline_id,
                'publisher_id': publisher_id,
                'message': 'Publisher disabled successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Disable pipeline publisher error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/publishers/status', methods=['GET'])
    def get_pipeline_publishers_status(pipeline_id):
        """Get the status of all publishers for a pipeline"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            publisher_states = node.pipeline_manager.get_pipeline_publisher_states(pipeline_id)
            if publisher_states is None:
                return jsonify({'error': 'Pipeline not found'}), 404

            return jsonify({
                'pipeline_id': pipeline_id,
                'publishers': publisher_states
            })
            
        except Exception as e:
            node.logger.error(f"Get pipeline publishers status error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/status', methods=['GET'])
    def get_pipeline_status(pipeline_id):
        """Get pipeline status"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
                
            pipeline = node.pipeline_manager.get_pipeline(pipeline_id)
            if not pipeline:
                return jsonify({'error': 'Pipeline not found'}), 404
            
            # Add runtime stats if available
            runtime_stats = {}
            if pipeline_id in node.pipeline_manager.active_pipelines:
                runtime_stats = node.pipeline_manager.active_pipelines[pipeline_id]
            
            return jsonify({
                'pipeline_id': pipeline_id,
                'status': pipeline['status'],
                'config': pipeline,
                'runtime_stats': runtime_stats
            })
            
        except Exception as e:
            node.logger.error(f"Get pipeline status error: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/pipeline/<pipeline_id>/stream')
    def stream_pipeline(pipeline_id):
        """Stream processed frames from a running pipeline"""
        def generate_frames():
            if not node.pipeline_manager:
                return
                
            frame_count = 0
            max_retries = 50
            retry_count = 0
            last_frame_time = 0
            frame_skip_threshold = 1.0 / 30
            
            pipeline_info = node.pipeline_manager.active_pipelines.get(pipeline_id)
            pipeline_instance = pipeline_info.get('pipeline_instance') if pipeline_info else None
            
            try:
                while retry_count < max_retries:
                    try:
                        if pipeline_id not in node.pipeline_manager.active_pipelines:
                            node.logger.warning(f"Pipeline {pipeline_id} not in active pipelines")
                            break
                        
                        pipeline_info = node.pipeline_manager.active_pipelines[pipeline_id]
                        pipeline_instance = pipeline_info.get('pipeline_instance')
                        
                        if not pipeline_instance:
                            retry_count += 1
                            time.sleep(0.1)
                            continue
                        
                        if hasattr(pipeline_instance, 'is_running') and not pipeline_instance.is_running():
                            break
                        
                        current_time = time.time()
                        if current_time - last_frame_time < frame_skip_threshold:
                            time.sleep(0.01)
                            continue
                        
                        frame = pipeline_instance.get_latest_frame()
                        
                        if frame is not None:
                            height, width = frame.shape[:2]
                            if width > 640:
                                scale = 640 / width
                                new_width = 640
                                new_height = int(height * scale)
                                frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
                            
                            ret, buffer = cv2.imencode('.jpg', frame, [
                                cv2.IMWRITE_JPEG_QUALITY, 70,
                                cv2.IMWRITE_JPEG_OPTIMIZE, 1
                            ])
                            if ret:
                                frame_bytes = buffer.tobytes()
                                yield (b'--frame\r\n'
                                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                                frame_count += 1
                                retry_count = 0
                                last_frame_time = current_time
                        else:
                            retry_count += 1
                            time.sleep(0.01)
                        
                    except Exception as e:
                        node.logger.error(f"Stream error for pipeline {pipeline_id}: {e}")
                        retry_count += 1
                        time.sleep(0.1)
            finally:
                if pipeline_instance and hasattr(pipeline_instance, 'stop_streaming'):
                    pipeline_instance.stop_streaming()
                node.logger.info(f"Stream ended for pipeline {pipeline_id}, streamed {frame_count} frames")
        
        try:
            if not node.pipeline_manager or pipeline_id not in node.pipeline_manager.active_pipelines:
                return jsonify({'error': 'Pipeline not found or not running'}), 404
            
            pipeline_info = node.pipeline_manager.active_pipelines.get(pipeline_id)
            if not pipeline_info or 'pipeline_instance' not in pipeline_info:
                return jsonify({'error': 'Pipeline instance not available'}), 404
            
            pipeline_instance = pipeline_info['pipeline_instance']
            
            if hasattr(pipeline_instance, 'is_running') and not pipeline_instance.is_running():
                return jsonify({'error': 'Pipeline is not running'}), 400
            
            if hasattr(pipeline_instance, 'is_initialized') and not pipeline_instance.is_initialized():
                return jsonify({'error': 'Pipeline is not initialized'}), 400
            
            if hasattr(pipeline_instance, 'start_streaming'):
                pipeline_instance.start_streaming()
            
            max_wait_time = 5.0
            wait_start = time.time()
            frame_available = False
            
            while time.time() - wait_start < max_wait_time:
                if pipeline_instance.get_latest_frame() is not None:
                    frame_available = True
                    break
                time.sleep(0.1)
            
            if not frame_available:
                if hasattr(pipeline_instance, 'stop_streaming'):
                    pipeline_instance.stop_streaming()
                return jsonify({'error': 'Pipeline is starting - no frames available yet. Please try again in a moment.'}), 503
            
            return Response(generate_frames(),
                          mimetype='multipart/x-mixed-replace; boundary=frame',
                          headers={'Cache-Control': 'no-cache, no-store, must-revalidate',
                                 'Pragma': 'no-cache',
                                 'Expires': '0'})
        except Exception as e:
            node.logger.error(f"Failed to start stream for pipeline {pipeline_id}: {e}")
            return jsonify({'error': 'Failed to start video stream'}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/stream/hq')
    def stream_pipeline_hq(pipeline_id):
        """High-quality stream for full preview modal"""
        def generate_frames():
            if not node.pipeline_manager:
                return
                
            frame_count = 0
            max_retries = 50
            retry_count = 0
            last_frame_time = 0
            frame_skip_threshold = 1.0 / 60
            
            pipeline_info = node.pipeline_manager.active_pipelines.get(pipeline_id)
            pipeline_instance = pipeline_info.get('pipeline_instance') if pipeline_info else None
            
            try:
                while retry_count < max_retries:
                    try:
                        if pipeline_id not in node.pipeline_manager.active_pipelines:
                            break
                        
                        pipeline_info = node.pipeline_manager.active_pipelines[pipeline_id]
                        pipeline_instance = pipeline_info.get('pipeline_instance')
                        
                        if not pipeline_instance:
                            retry_count += 1
                            time.sleep(0.05)
                            continue
                        
                        if hasattr(pipeline_instance, 'is_running') and not pipeline_instance.is_running():
                            break
                        
                        current_time = time.time()
                        if current_time - last_frame_time < frame_skip_threshold:
                            time.sleep(0.005)
                            continue
                        
                        frame = pipeline_instance.get_latest_frame()
                        
                        if frame is not None:
                            height, width = frame.shape[:2]
                            if width > 1280:
                                scale = 1280 / width
                                new_width = 1280
                                new_height = int(height * scale)
                                frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
                            
                            ret, buffer = cv2.imencode('.jpg', frame, [
                                cv2.IMWRITE_JPEG_QUALITY, 85,
                                cv2.IMWRITE_JPEG_OPTIMIZE, 1
                            ])
                            if ret:
                                frame_bytes = buffer.tobytes()
                                yield (b'--frame\r\n'
                                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                                frame_count += 1
                                retry_count = 0
                                last_frame_time = current_time
                        else:
                            retry_count += 1
                            time.sleep(0.005)
                        
                    except Exception as e:
                        node.logger.error(f"HQ Stream error for pipeline {pipeline_id}: {e}")
                        retry_count += 1
                        time.sleep(0.05)
            finally:
                if pipeline_instance and hasattr(pipeline_instance, 'stop_streaming'):
                    pipeline_instance.stop_streaming()
                node.logger.info(f"HQ Stream ended for pipeline {pipeline_id}, streamed {frame_count} frames")
        
        try:
            if not node.pipeline_manager or pipeline_id not in node.pipeline_manager.active_pipelines:
                return jsonify({'error': 'Pipeline not found or not running'}), 404
            
            pipeline_info = node.pipeline_manager.active_pipelines.get(pipeline_id)
            if not pipeline_info or 'pipeline_instance' not in pipeline_info:
                return jsonify({'error': 'Pipeline instance not available'}), 404
            
            pipeline_instance = pipeline_info['pipeline_instance']
            
            if hasattr(pipeline_instance, 'is_running') and not pipeline_instance.is_running():
                return jsonify({'error': 'Pipeline is not running'}), 400
            
            if hasattr(pipeline_instance, 'is_initialized') and not pipeline_instance.is_initialized():
                return jsonify({'error': 'Pipeline is not initialized'}), 400
            
            if hasattr(pipeline_instance, 'start_streaming'):
                pipeline_instance.start_streaming()
            
            max_wait_time = 5.0
            wait_start = time.time()
            frame_available = False
            
            while time.time() - wait_start < max_wait_time:
                if pipeline_instance.get_latest_frame() is not None:
                    frame_available = True
                    break
                time.sleep(0.1)
            
            if not frame_available:
                if hasattr(pipeline_instance, 'stop_streaming'):
                    pipeline_instance.stop_streaming()
                return jsonify({'error': 'Pipeline is starting - no frames available yet. Please try again in a moment.'}), 503
            
            return Response(generate_frames(),
                          mimetype='multipart/x-mixed-replace; boundary=frame',
                          headers={'Cache-Control': 'no-cache, no-store, must-revalidate',
                                 'Pragma': 'no-cache',
                                 'Expires': '0'})
        except Exception as e:
            node.logger.error(f"Failed to start HQ stream for pipeline {pipeline_id}: {e}")
            return jsonify({'error': 'Failed to start HQ video stream'}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/thumbnail')
    def get_pipeline_thumbnail(pipeline_id):
        """Serve pipeline thumbnail image"""
        try:
            from flask import send_file
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
            
            thumbnail_path = node.pipeline_manager.get_pipeline_thumbnail_path(pipeline_id)
            
            if not thumbnail_path:
                return jsonify({'error': 'Thumbnail not found'}), 404
            
            return send_file(thumbnail_path, mimetype='image/jpeg')
            
        except Exception as e:
            node.logger.error(f"Error serving thumbnail for pipeline {pipeline_id}: {e}")
            return jsonify({'error': 'Failed to serve thumbnail'}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/thumbnail/exists')
    def check_pipeline_thumbnail(pipeline_id):
        """Check if pipeline has a thumbnail"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
            
            has_thumbnail = node.pipeline_manager.has_pipeline_thumbnail(pipeline_id)
            return jsonify({'has_thumbnail': has_thumbnail})
            
        except Exception as e:
            node.logger.error(f"Error checking thumbnail for pipeline {pipeline_id}: {e}")
            return jsonify({'error': 'Failed to check thumbnail'}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/thumbnail/generate', methods=['POST'])
    def generate_pipeline_thumbnail(pipeline_id):
        """Generate a fresh thumbnail for a pipeline from current frame"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
            
            pipeline = node.pipeline_manager.get_pipeline(pipeline_id)
            if not pipeline:
                return jsonify({'error': 'Pipeline not found'}), 404
            
            success = node.pipeline_manager.generate_pipeline_thumbnail(pipeline_id)
            
            if success:
                has_thumbnail = node.pipeline_manager.has_pipeline_thumbnail(pipeline_id)
                thumbnail_path = node.pipeline_manager.get_pipeline_thumbnail_path(pipeline_id)
                
                return jsonify({
                    'success': True,
                    'message': 'Thumbnail generated successfully',
                    'pipeline_id': pipeline_id,
                    'has_thumbnail': has_thumbnail,
                    'thumbnail_path': thumbnail_path if has_thumbnail else None
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to generate thumbnail - pipeline may not be running or accessible',
                    'pipeline_id': pipeline_id
                }), 500
            
        except Exception as e:
            node.logger.error(f"Generate thumbnail error for pipeline {pipeline_id}: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/<pipeline_id>/export', methods=['GET'])
    def export_pipeline(pipeline_id):
        """Export a pipeline as a ZIP file containing configuration and model files"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
            
            pipeline = node.pipeline_manager.get_pipeline(pipeline_id)
            if not pipeline:
                return jsonify({'error': 'Pipeline not found'}), 404
            
            zip_fd, zip_path = tempfile.mkstemp(suffix='.zip')
            
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    config_data = {
                        'name': pipeline['name'],
                        'description': pipeline.get('description', ''),
                        'frame_source': pipeline['frame_source'],
                        'model': pipeline['model'],
                        'destinations': pipeline.get('destinations', []),
                        'export_metadata': {
                            'exported_by': node.node_name,
                            'export_date': datetime.now().isoformat(),
                            'pipeline_id': pipeline_id,
                            'version': '1.0'
                        }
                    }
                    
                    config_file = os.path.join(temp_dir, 'pipeline_config.json')
                    with open(config_file, 'w') as f:
                        json.dump(config_data, f, indent=2)
                    
                    models_dir = os.path.join(temp_dir, 'models')
                    os.makedirs(models_dir, exist_ok=True)
                    
                    model_files_included = []
                    if 'model' in pipeline and 'id' in pipeline['model']:
                        model_id = pipeline['model']['id']
                        model_metadata = node.model_repo.get_model_metadata(model_id)
                        
                        if model_metadata:
                            model_path = node.model_repo.get_model_path(model_id)
                            if model_path and os.path.exists(model_path):
                                model_filename = model_metadata['stored_filename']
                                dest_path = os.path.join(models_dir, model_filename)
                                shutil.copy2(model_path, dest_path)
                                model_files_included.append(model_filename)
                                
                                model_dir = os.path.dirname(model_path)
                                model_base_name = os.path.splitext(model_metadata['stored_filename'])[0]
                                
                                for file in os.listdir(model_dir):
                                    if file.startswith(model_base_name) and file != model_metadata['stored_filename']:
                                        src_file = os.path.join(model_dir, file)
                                        dest_file = os.path.join(models_dir, file)
                                        if os.path.isfile(src_file):
                                            shutil.copy2(src_file, dest_file)
                                            model_files_included.append(file)
                                
                                model_metadata_file = os.path.join(models_dir, 'model_metadata.json')
                                with open(model_metadata_file, 'w') as f:
                                    json.dump(model_metadata, f, indent=2)
                                model_files_included.append('model_metadata.json')
                    
                    config_data['export_metadata']['model_files'] = model_files_included
                    
                    with open(config_file, 'w') as f:
                        json.dump(config_data, f, indent=2)
                    
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        zipf.write(config_file, 'pipeline_config.json')
                        
                        for root, dirs, files in os.walk(models_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arc_name = os.path.join('models', os.path.relpath(file_path, models_dir))
                                zipf.write(file_path, arc_name)
                
                os.close(zip_fd)
                
                import re
                zip_filename = f"{pipeline['name'].replace(' ', '_').replace('/', '_')}_export.zip"
                zip_filename = re.sub(r'[<>:"/\\|?*]', '_', zip_filename)
                
                node.logger.info(f"Pipeline exported: {pipeline['name']} ({pipeline_id})")
                
                with open(zip_path, 'rb') as f:
                    zip_contents = f.read()
                
                try:
                    os.unlink(zip_path)
                except:
                    pass
                
                response = Response(
                    zip_contents,
                    mimetype='application/zip',
                    headers={
                        'Content-Disposition': f'attachment; filename="{zip_filename}"',
                        'Content-Length': str(len(zip_contents))
                    }
                )
                return response
                
            except Exception as e:
                try:
                    os.close(zip_fd)
                    os.unlink(zip_path)
                except:
                    pass
                raise e
                
        except Exception as e:
            node.logger.error(f"Export pipeline error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/pipeline/import', methods=['POST'])
    def import_pipeline():
        """Import a pipeline from an uploaded ZIP file"""
        try:
            if not node.pipeline_manager:
                return jsonify({'error': 'Pipeline manager not available'}), 503
            
            if 'file' not in request.files:
                return jsonify({'error': 'No file uploaded'}), 400
            
            file = request.files['file']
            if file.filename == '' or file.filename is None:
                return jsonify({'error': 'No file selected'}), 400
            
            if not file.filename.endswith('.zip'):
                return jsonify({'error': 'File must be a ZIP archive'}), 400
            
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, file.filename)
                file.save(zip_path)
                
                extract_dir = os.path.join(temp_dir, 'extracted')
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(extract_dir)
                
                config_file = os.path.join(extract_dir, 'pipeline_config.json')
                if not os.path.exists(config_file):
                    return jsonify({'error': 'Invalid pipeline export: missing pipeline_config.json'}), 400
                
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                
                required_fields = ['name', 'frame_source', 'model']
                for field in required_fields:
                    if field not in config_data:
                        return jsonify({'error': f'Invalid pipeline configuration: missing {field}'}), 400
                
                models_dir = os.path.join(extract_dir, 'models')
                new_model_id = None
                
                if os.path.exists(models_dir):
                    model_metadata_file = os.path.join(models_dir, 'model_metadata.json')
                    model_metadata = None
                    if os.path.exists(model_metadata_file):
                        with open(model_metadata_file, 'r') as f:
                            model_metadata = json.load(f)
                    
                    model_files = [f for f in os.listdir(models_dir) if f != 'model_metadata.json']
                    if model_files:
                        main_model_file = model_files[0]
                        if model_metadata and 'stored_filename' in model_metadata:
                            main_model_file = model_metadata['stored_filename']
                            if main_model_file not in model_files:
                                main_model_file = model_files[0]
                        
                        model_file_path = os.path.join(models_dir, main_model_file)
                        original_filename = model_metadata.get('original_filename', main_model_file) if model_metadata else main_model_file
                        engine_type = config_data['model'].get('engine_type', 'unknown')
                        description = f"Imported with pipeline: {config_data['name']}"
                        imported_name = model_metadata.get('name', os.path.splitext(original_filename)[0]) if model_metadata else os.path.splitext(original_filename)[0]
                        
                        new_model_id = node.model_repo.store_model(
                            model_file_path, 
                            original_filename, 
                            engine_type, 
                            description,
                            imported_name
                        )
                        
                        new_model_metadata = node.model_repo.get_model_metadata(new_model_id)
                        if new_model_metadata:
                            new_model_dir = os.path.dirname(new_model_metadata['stored_path'])
                            new_model_base = os.path.splitext(new_model_metadata['stored_filename'])[0]
                            
                            for model_file in model_files:
                                if model_file != main_model_file and model_file != 'model_metadata.json':
                                    src_path = os.path.join(models_dir, model_file)
                                    file_ext = os.path.splitext(model_file)[1]
                                    dest_filename = f"{new_model_base}{file_ext}"
                                    dest_path = os.path.join(new_model_dir, dest_filename)
                                    shutil.copy2(src_path, dest_path)
                
                if new_model_id:
                    config_data['model']['id'] = new_model_id
                
                original_name = config_data['name']
                pipeline_name = original_name
                existing_pipelines = node.pipeline_manager.list_pipelines()
                existing_names = [p['name'] for p in existing_pipelines.values()]
                
                counter = 1
                while pipeline_name in existing_names:
                    pipeline_name = f"{original_name} (imported {counter})"
                    counter += 1
                
                config_data['name'] = pipeline_name
                
                if 'export_metadata' in config_data:
                    del config_data['export_metadata']
                
                pipeline_id = node.pipeline_manager.create_pipeline(config_data)
                
                node.logger.info(f"Pipeline imported: {pipeline_name} ({pipeline_id})")
                
                return jsonify({
                    'status': 'imported',
                    'pipeline_id': pipeline_id,
                    'pipeline_name': pipeline_name,
                    'model_id': new_model_id,
                    'message': f'Pipeline "{pipeline_name}" imported successfully'
                })
                
        except Exception as e:
            node.logger.error(f"Import pipeline error: {str(e)}")
            return jsonify({'error': str(e)}), 500
