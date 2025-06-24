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
            if tags.get("SeriesDescription") == "Automated Diagnostic Findings":
                return True
        return False
    except Exception as e:
        print(f"Error checking AI marker: {str(e)}")
        return False


def GetStudyInstanceUID(study_id):
    """Get the DICOM StudyInstanceUID from an Orthanc study ID"""
    try:
        # Get the study information
        study_info = json.loads(orthanc.RestApiGet(f"/studies/{study_id}"))
        # Get the MainDicomTags which contains the StudyInstanceUID
        main_tags = study_info.get("MainDicomTags", {})
        study_instance_uid = main_tags.get("StudyInstanceUID")
        if not study_instance_uid:
            print(f"Warning: StudyInstanceUID not found for study {study_id}")
            return None
        return study_instance_uid
    except Exception as e:
        print(f"Error getting StudyInstanceUID: {str(e)}")
        return None


def ListModalities():
    """List all configured DICOM modalities"""
    try:
        modalities = json.loads(orthanc.RestApiGet("/modalities"))
        print("Configured DICOM modalities:")
        for modality in modalities:
            modality_info = json.loads(orthanc.RestApiGet(f"/modalities/{modality}"))
            print(f"  - {modality}: {modality_info.get('Host', 'unknown')}:{modality_info.get('Port', 'unknown')} (AET: {modality_info.get('AET', 'unknown')})")
        return modalities
    except Exception as e:
        print(f"Error listing modalities: {str(e)}")
        return []


def SendToAiDicom(output, uri, **request):
    """REST endpoint to send a study to target server using DICOM protocol"""
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

        # List all configured modalities before proceeding
        ListModalities()

        # Configure DICOM modality if target_url is provided
        if target_url:
            try:
                # Parse the target URL to extract host, port, and AE Title
                # Expected format: host:port/AET
                print(f"Parsing target URL: {target_url}")

                # First, check if the modality already exists
                try:
                    existing_modality = json.loads(orthanc.RestApiGet(f"/modalities/{target}"))
                    print(f"Modality {target} already exists with configuration: {existing_modality}")

                    # Delete the existing modality to ensure a clean configuration
                    orthanc.RestApiDelete(f"/modalities/{target}")
                    print(f"Deleted existing modality {target}")
                except:
                    # Modality doesn't exist, which is fine
                    pass

                # Parse the URL parts
                url_parts = target_url.split('/')
                if len(url_parts) >= 2:
                    host_port = url_parts[0].split(':')
                    host = host_port[0]
                    port = int(host_port[1]) if len(host_port) > 1 else 104  # Default DICOM port
                    aet = url_parts[1] if len(url_parts) > 1 else target  # Use target name as AE Title if not specified

                    print(f"Extracted host: {host}, port: {port}, AET: {aet}")

                    # Configure the DICOM modality with more detailed settings
                    modality_config = {
                        "AET": aet,
                        "Host": host,
                        "Port": port,
                        "Manufacturer": "Generic",
                        "AllowEcho": True,
                        "AllowFind": True,
                        "AllowGet": True,
                        "AllowMove": True,
                        "AllowStore": True,
                        "CheckCalledAet": False,
                        "DicomAet": "ORTHANC",  # Your Orthanc's AE Title
                        "DicomCheckCalledAet": False,
                        "DicomPort": 4242,  # Your Orthanc's DICOM port
                        "DicomWeb": {
                            "Enable": False,
                            "Root": "/dicom-web/",
                            "Ssl": False,
                            "Studies": True,
                            "EnableWado": False,
                            "WadoRoot": "/wado",
                            "WadoMetadata": {
                                "Enable": False,
                                "MaxResults": 100
                            }
                        },
                        "Timeout": 60,  # Increase timeout to 60 seconds
                        "ConcurrentOperations": 1,  # Limit to 1 concurrent operation
                        "RetryCount": 3,  # Retry up to 3 times
                        "RetryDelay": 5,  # Wait 5 seconds between retries
                        "TransferSyntaxes": [
                            "1.2.840.10008.1.2.1",  # Explicit VR Little Endian
                            "1.2.840.10008.1.2",    # Implicit VR Little Endian
                            "1.2.840.10008.1.2.2"   # Explicit VR Big Endian
                        ]
                    }

                    # Add the modality configuration
                    orthanc.RestApiPut(f'/modalities/{target}', json.dumps(modality_config))
                    print(f"Successfully configured DICOM modality: {target}")

                    # Verify the configuration
                    try:
                        configured_modality = json.loads(orthanc.RestApiGet(f"/modalities/{target}"))
                        print(f"Verified modality configuration: {configured_modality}")
                    except Exception as e:
                        print(f"Warning: Failed to verify modality configuration: {str(e)}")
                else:
                    print(f"Invalid target URL format: {target_url}")
            except Exception as e:
                print(f"Warning: Failed to configure DICOM modality: {str(e)}")
                # Continue anyway as the modality might already be configured

        # Try to send the study using DICOM modality
        try:
            # Use the Orthanc study ID directly - this is what the API expects
            print(f"Attempting to send study {study_id} to DICOM modality {target}")
            orthanc.RestApiPost(f'/modalities/{target}/store', json.dumps([study_id]))
            print(f"Successfully sent study {study_id} to DICOM modality {target}")

            response_data = {
                "status": "success",
                "message": f"Successfully sent study {study_id} to {target} using DICOM protocol",
                "study_id": study_id,
                "target": target
            }
            output.AnswerBuffer(json.dumps(response_data), 'application/json')
        except Exception as e:
            error_message = f"Failed to send study using DICOM protocol: {str(e)}"
            print(error_message)
            error_response = {
                "status": "error",
                "message": error_message
            }
            output.AnswerBuffer(json.dumps(error_response), 'application/json')

    except Exception as e:
        error_message = str(e)
        error_response = {
            "status": "error",
            "message": f"Error sending study: {error_message}"
        }
        output.AnswerBuffer(json.dumps(error_response), 'application/json')


def SendToAiDicomWeb(output, uri, **request):
    """REST endpoint to send a study to target server using DICOMweb protocol"""
    if request['method'] != 'POST':
        output.SendMethodNotAllowed('POST')
        return

    try:
        print("SendToAiDicomWeb: Starting processing of request")

        # Parse the POST body
        body = json.loads(request['body'])
        study_id = body.get('study_id')
        target = body.get('target')
        target_url = body.get('target_url')

        print(f"SendToAiDicomWeb: Request parameters - study_id: {study_id}, target: {target}, target_url: {target_url}")

        if not study_id or not target:
            print("SendToAiDicomWeb: Missing required parameters")
            output.SendHttpStatus(400, 'Missing study_id or target in request body')
            return

        if not target_url:
            print("SendToAiDicomWeb: Missing target_url parameter")
            output.SendHttpStatus(400, 'Missing target_url in request body')
            return

        # Verify study_id exists in Orthanc
        try:
            study_info = json.loads(orthanc.RestApiGet(f"/studies/{study_id}"))
            print(f"SendToAiDicomWeb: Valid study found with ID {study_id}")
            print(f"SendToAiDicomWeb: Study contains {len(study_info['Series'])} series and {study_info['PatientMainDicomTags'].get('PatientName', 'Unknown')} patient")
        except Exception as e:
            print(f"SendToAiDicomWeb: Error verifying study existence: {str(e)}")
            output.SendHttpStatus(404, f"Study with ID {study_id} not found: {str(e)}")
            return

        if IsAiProcessed(study_id):
            print("SendToAiDicomWeb: Study already contains AI results")
            output.SendHttpStatus(400, 'Study already contains AI results')
            return

        try:
            # Configure the DICOMweb server
            print(f"SendToAiDicomWeb: Configuring DICOMweb server {target} with URL {target_url}")

            # Create server configuration
            server_config = {
                "Url": target_url,
                "Username": body.get('username', ''),
                "Password": body.get('password', ''),
                "HttpHeaders": {}
            }

            # Configure the server using direct HTTP request
            config_response = requests.put(
                f"http://localhost:8042/dicom-web/servers/{target}",
                json=server_config
            )

            if config_response.status_code not in [200, 201, 204]:
                error_message = f"Error configuring DICOMweb server: {config_response.text}"
                print(f"SendToAiDicomWeb: {error_message}")
                output.SendHttpStatus(500, error_message)
                return

            print(f"SendToAiDicomWeb: Successfully configured DICOMweb server: {target}")

            # Get all instances from the study
            instances = json.loads(orthanc.RestApiGet(f"/studies/{study_id}/instances"))
            print(f"SendToAiDicomWeb: Found {len(instances)} instances in study")

            # Prepare the STOW-RS request body
            stow_body = {
                "Resources": [instance['ID'] for instance in instances]
            }
            print(f"SendToAiDicomWeb: Prepared STOW-RS request with {len(stow_body['Resources'])} instances")

            # Send the request using direct HTTP request
            stow_response = requests.post(
                f"http://localhost:8042/dicom-web/servers/{target}/stow",
                json=stow_body
            )

            print(f"SendToAiDicomWeb: STOW-RS response status: {stow_response.status_code}")
            print(f"SendToAiDicomWeb: STOW-RS response: {stow_response.text}")

            # Process response
            if stow_response.status_code in [200, 201, 202]:
                try:
                    response_data = stow_response.json()
                    print("SendToAiDicomWeb: Successfully sent study via DICOMweb")

                    # Return success response
                    success_response = {
                        "status": "success",
                        "message": f"Successfully sent study {study_id} to {target} using DICOMweb protocol",
                        "study_id": study_id,
                        "target": target,
                        "response": response_data
                    }
                    print("SendToAiDicomWeb: Returning success response")
                    output.AnswerBuffer(json.dumps(success_response), 'application/json')
                except Exception as e:
                    error_message = f"Error processing STOW-RS response: {str(e)}"
                    print(f"SendToAiDicomWeb: {error_message}")
                    output.SendHttpStatus(500, error_message)
            else:
                error_message = f"DICOMweb error: {stow_response.status_code} - {stow_response.text}"
                print(f"SendToAiDicomWeb: {error_message}")
                output.SendHttpStatus(stow_response.status_code, error_message)

        except Exception as e:
            error_message = f"Error during STOW-RS request: {str(e)}"
            print(f"SendToAiDicomWeb: {error_message}")
            output.SendHttpStatus(500, error_message)

    except Exception as e:
        error_message = f"Error processing request: {str(e)}"
        print(f"SendToAiDicomWeb: {error_message}")
        output.SendHttpStatus(500, error_message)


def SendToAi(output, uri, **request):
    """REST endpoint to send a study to target server using DICOMWeb protocol"""
    # This is now just a wrapper around SendToAiDicomWeb for backward compatibility
    print("giving control to SendToAiDicomWeb")
    SendToAiDicomWeb(output, uri, **request)


# Register the REST endpoints
orthanc.RegisterRestCallback('/send-to-ai', SendToAi)
orthanc.RegisterRestCallback('/send-to-ai-dicom', SendToAiDicom)
orthanc.RegisterRestCallback('/send-to-ai-dicomweb', SendToAiDicomWeb)
