import json

import orthanc
import requests


def IsAiProcessed(study_id):
    """Check if any instance in study has AI marker"""
    try:
        instances = json.loads(orthanc.RestApiGet(f"/studies/{study_id}/instances"))
        for instance in instances:
            tags = json.loads(
                orthanc.RestApiGet(f"/instances/{instance['ID']}/tags?simplify")
            )
            if tags.get("SeriesDescription") == "AI_Processed":
                return True
        return False
    except Exception as e:
        print(f"Error checking AI marker: {str(e)}")
        return False


def SendToAi(output, uri, **request):
    """REST endpoint to send a study to target server"""
    if request['method'] != 'POST':
        output.SendMethodNotAllowed('POST')
        return
    
    try:
        # Parse the POST body
        body = json.loads(request['body'])
        study_id = body.get('study_id')
        target = body.get('target')
        target_url = body.get('target_url')
        
        if not study_id or not target:
            output.SendHttpStatus(400, 'Missing study_id or target in request body')
            return
            
        if IsAiProcessed(study_id):
            output.SendHttpStatus(400, 'Study already contains AI results')
            return

        # First, try to register the peer if target_url is provided
        if target_url:
            try:
                peer_config = {
                    "Url": target_url,
                    "Username": body.get('username', ''),  # Optional
                    "Password": body.get('password', ''),  # Optional
                    "HttpHeaders": {}  # Can be extended with custom headers if needed
                }
                orthanc.RestApiPut(f'/peers/{target}', json.dumps(peer_config))
            except Exception as e:
                print(f"Warning: Failed to register peer: {str(e)}")
                # Continue anyway as the peer might already be configured
        
        try:
            # Try DICOMweb approach first (for pre-configured servers)
            forward_request = {"Resources": [study_id]}
            response = requests.post(
                f"http://localhost:8042/dicom-web/servers/{target}/stow/",
                json=forward_request,
                timeout=10
            )
            response.raise_for_status()
        except Exception as e:
            # If DICOMweb fails, try peer store approach
            orthanc.RestApiPost(f'/peers/{target}/store', study_id)
        
        response_data = {
            "status": "success",
            "message": f"Successfully sent study {study_id} to {target}",
            "study_id": study_id,
            "target": target
        }
        output.AnswerBuffer(json.dumps(response_data), 'application/json')
        
    except Exception as e:
        error_message = str(e)
        error_response = {
            "status": "error",
            "message": f"Error sending study: {error_message}"
        }
        output.AnswerBuffer(json.dumps(error_response), 'application/json')

# Register the REST endpoint
orthanc.RegisterRestCallback('/send-to-ai', SendToAi)
