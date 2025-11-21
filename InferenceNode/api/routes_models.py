"""
Model management API routes for InferenceNode
Handles model upload, download, listing, and deletion
"""
import os
import tempfile
from datetime import datetime
from flask import request, jsonify


def register_model_routes(app, node):
    """Register model management routes"""
    
    @app.route('/api/models/upload', methods=['POST'])
    def upload_model():
        """Upload a model file"""
        try:
            if 'file' not in request.files:
                return jsonify({'error': 'No file provided'}), 400
            
            file = request.files['file']
            engine_type = request.form.get('engine_type', 'custom')
            description = request.form.get('description', '')
            name = request.form.get('name', '')
            
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            # Save uploaded file temporarily
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, file.filename or 'uploaded_model')
            file.save(temp_path)
            
            try:
                # Store model in repository
                model_id = node.model_repo.store_model(
                    temp_path, 
                    file.filename or 'uploaded_model',
                    engine_type,
                    description,
                    name
                )
                
                node.logger.info(f"Model uploaded successfully: {model_id}")
                
                return jsonify({
                    'model_id': model_id, 
                    'status': 'uploaded',
                    'message': f'Model {file.filename} uploaded successfully'
                })
                
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            
        except Exception as e:
            node.logger.error(f"Model upload error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/media/upload-video', methods=['POST'])
    def upload_video():
        """Upload a video file to the media directory"""
        try:
            if 'file' not in request.files:
                return jsonify({'error': 'No file provided'}), 400
            
            file = request.files['file']
            
            if file.filename == '' or file.filename is None:
                return jsonify({'error': 'No file selected'}), 400
            
            # Validate file extension
            allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg'}
            file_ext = os.path.splitext(file.filename)[1].lower()
            
            if file_ext not in allowed_extensions:
                return jsonify({'error': f'Invalid file type. Allowed types: {", ".join(allowed_extensions)}'}), 400
            
            # Create media directory if it doesn't exist
            media_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'media')
            os.makedirs(media_dir, exist_ok=True)
            
            # Generate unique filename to avoid conflicts
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_filename = f"{timestamp}_{file.filename}"
            file_path = os.path.join(media_dir, safe_filename)
            
            # Save the uploaded file
            file.save(file_path)
            
            node.logger.info(f"Video file uploaded successfully: {safe_filename}")
            
            return jsonify({
                'status': 'uploaded',
                'filename': safe_filename,
                'path': file_path,
                'message': f'Video {file.filename} uploaded successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Video upload error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/models/download-ultralytics', methods=['POST'])
    def download_ultralytics_model():
        """Download a model from Ultralytics and add it to the repository"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            
            model_name = data.get('model_name', '').strip()
            description = data.get('description', '').strip()
            name = data.get('name', '').strip()
            
            if not model_name:
                return jsonify({'error': 'Model name is required'}), 400
            
            node.logger.info(f"Starting download of Ultralytics model: {model_name}")
            
            try:
                # Import ultralytics - this should be available if user selected ultralytics
                from ultralytics import YOLO
            except ImportError:
                return jsonify({'error': 'Ultralytics package not available. Please install ultralytics: pip install ultralytics'}), 500
            
            # Track if model was downloaded to project root (for cleanup)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root_model_path = os.path.join(project_root, model_name)
            model_was_in_root_before = os.path.exists(project_root_model_path)
            
            try:
                # Download the model using ultralytics
                node.logger.info(f"Downloading {model_name} from Ultralytics...")
                
                # Initialize YOLO with the model name - this will download it automatically
                model = YOLO(model_name)
                
                # Get the actual model file path after download
                # Ultralytics downloads models to a cache directory or current directory
                model_path = None
                
                # Try to get model path from the YOLO object
                if hasattr(model, 'model_path') and isinstance(model.model_path, str):
                    model_path = model.model_path
                elif hasattr(model, 'ckpt_path') and isinstance(model.ckpt_path, str):
                    model_path = model.ckpt_path
                
                if not model_path or not os.path.exists(model_path):
                    # Try to find the model in ultralytics cache
                    cache_dir = os.path.join(os.path.expanduser('~'), '.ultralytics', 'cache')
                    potential_path = os.path.join(cache_dir, model_name)
                    
                    if os.path.exists(potential_path):
                        model_path = potential_path
                    # Check if it was downloaded to project root
                    elif os.path.exists(project_root_model_path):
                        model_path = project_root_model_path
                        node.logger.info(f"Found model in project root: {project_root_model_path}")
                    else:
                        # Search for the model file in the cache directory
                        for root, dirs, files in os.walk(cache_dir):
                            for file in files:
                                if file == model_name:
                                    model_path = os.path.join(root, file)
                                    break
                            if model_path:
                                break
                
                if not model_path or not isinstance(model_path, str) or not os.path.exists(model_path):
                    return jsonify({'error': f'Failed to locate downloaded model: {model_name}'}), 500
                
                # Generate description if not provided
                if not description:
                    description = f"Pre-trained {model_name} model from Ultralytics"
                
                # Generate name if not provided - use model name without extension
                if not name:
                    name = os.path.splitext(model_name)[0]
                
                # Store the model in the repository
                model_id = node.model_repo.store_model(
                    model_path,
                    model_name,
                    'ultralytics',  # Engine type
                    description,
                    name
                )
                
                node.logger.info(f"Ultralytics model downloaded and stored successfully: {model_id}")
                
                return jsonify({
                    'model_id': model_id,
                    'status': 'downloaded',
                    'model_name': model_name,
                    'message': f'Model {model_name} downloaded and uploaded successfully'
                })
                
            except Exception as download_error:
                node.logger.error(f"Error downloading Ultralytics model {model_name}: {str(download_error)}")
                return jsonify({'error': f'Failed to download model: {str(download_error)}'}), 500
                
            finally:
                # Clean up model file from project root if it was downloaded there
                try:
                    # Only delete if the file exists in project root AND it wasn't there before download
                    if (os.path.exists(project_root_model_path) and 
                        not model_was_in_root_before and 
                        os.path.isfile(project_root_model_path)):
                        os.remove(project_root_model_path)
                        node.logger.info(f"Cleaned up downloaded model from project root: {project_root_model_path}")
                except Exception as cleanup_error:
                    node.logger.warning(f"Failed to cleanup model file from project root: {cleanup_error}")
            
        except Exception as e:
            node.logger.error(f"Download Ultralytics model error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/models', methods=['GET'])
    def list_models():
        """List all uploaded models"""
        try:
            models = node.model_repo.list_models()
            stats = node.model_repo.get_storage_stats()
            
            return jsonify({
                'models': models,
                'stats': stats
            })
            
        except Exception as e:
            node.logger.error(f"List models error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/models/<model_id>', methods=['GET'])
    def get_model_info(model_id):
        """Get detailed information about a specific model"""
        try:
            metadata = node.model_repo.get_model_metadata(model_id)
            if not metadata:
                return jsonify({'error': 'Model not found'}), 404
            
            return jsonify(metadata)
            
        except Exception as e:
            node.logger.error(f"Get model info error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/models/<model_id>', methods=['DELETE'])
    def delete_model(model_id):
        """Delete a model from the repository"""
        try:
            success = node.model_repo.delete_model(model_id)
            if not success:
                return jsonify({'error': 'Model not found or could not be deleted'}), 404
            
            return jsonify({
                'status': 'deleted',
                'model_id': model_id,
                'message': f'Model {model_id} deleted successfully'
            })
            
        except Exception as e:
            node.logger.error(f"Delete model error: {str(e)}")
            return jsonify({'error': str(e)}), 500
