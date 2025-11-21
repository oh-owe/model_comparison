"""
Hardware detection API routes for InferenceNode
Handles hardware information and device formatting
"""

from flask import jsonify, request


def register_hardware_routes(app, node):
    """Register all hardware-related routes with the Flask app"""
    
    @app.route('/api/hardware', methods=['GET'])
    def get_hardware_info():
        """Get detailed hardware information and available devices"""
        try:
            # Get Intel GPU details for enhanced display
            intel_gpu_details = node.hardware_detector.get_intel_gpu_details()
            intel_gpu_info = {}
            for device_id, details in intel_gpu_details.items():
                intel_gpu_info[device_id] = {
                    'name': details['name'],
                    'type': details['type'],
                    'is_igpu': details['is_igpu'],
                    'friendly_name': node.hardware_detector.get_intel_gpu_friendly_name(device_id),
                    'description': node.hardware_detector.get_intel_gpu_description(device_id)
                }
            
            # Get NVIDIA GPU details for enhanced display
            nvidia_gpu_details = node.hardware_detector.get_nvidia_gpu_details()
            nvidia_gpu_info = {}
            for device_id, details in nvidia_gpu_details.items():
                nvidia_gpu_info[device_id] = {
                    'name': details['name'],
                    'uuid': details['uuid'],
                    'friendly_name': node.hardware_detector.get_nvidia_gpu_friendly_name(device_id),
                    'description': node.hardware_detector.get_nvidia_gpu_description(device_id)
                }
            
            hardware_info = {
                'detected_hardware': node.hardware_detector.hardware_info,
                'available_devices': node.hardware_detector.available_devices,
                'optimal_device': node.hardware_detector.get_optimal_device_for_hardware(),
                'intel_gpu_details': intel_gpu_info,
                'nvidia_gpu_details': nvidia_gpu_info,
                'device_capabilities': {
                    'nvidia_gpu': node.hardware_detector.has_nvidia_gpu(),
                    'nvidia_gpu_count': node.hardware_detector.get_nvidia_gpu_count(),
                    'intel_gpu': node.hardware_detector.has_intel_gpu(),
                    'intel_gpu_count': node.hardware_detector.get_intel_gpu_count(),
                    'intel_cpu': node.hardware_detector.has_intel_cpu(),
                    'intel_npu': node.hardware_detector.has_intel_npu(),
                    'amd_gpu': node.hardware_detector.has_amd_gpu(),
                    'amd_cpu': node.hardware_detector.has_amd_cpu(),
                    'apple_silicon': node.hardware_detector.has_apple_silicon(),
                    'apple_neural_engine': node.hardware_detector.has_apple_neural_engine()
                }
            }
            return jsonify(hardware_info)
        except Exception as e:
            node.logger.error(f"Hardware info error: {str(e)}")
            return jsonify({'error': f'Failed to get hardware info: {str(e)}'}), 500
    
    @app.route('/api/hardware/format-device', methods=['POST'])
    def format_device_for_engine():
        """Format a device string for a specific inference engine"""
        try:
            data = request.get_json()
            if not data or 'engine' not in data or 'device' not in data:
                return jsonify({'error': 'Missing required fields: engine and device'}), 400
            
            engine = data['engine']
            device = data['device']
            
            formatted_device = node.hardware_detector.format_for(engine, device)
            
            return jsonify({
                'original_device': device,
                'formatted_device': formatted_device,
                'engine': engine
            })
            
        except Exception as e:
            node.logger.error(f"Format device error: {str(e)}")
            return jsonify({'error': f'Failed to format device: {str(e)}'}), 500
