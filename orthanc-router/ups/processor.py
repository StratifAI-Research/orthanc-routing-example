"""
UPS Workitem processor - executes AI inference tasks
"""

import os
import io
import json
import time
import requests
from datetime import datetime

import orthanc
from pydicom import dcmread
from pydicom.uid import generate_uid

from ups.storage import ups_storage


# Get MODEL_BACKEND_URL from environment (configured per router instance in docker-compose)
MODEL_BACKEND_URL = os.environ.get("MODEL_BACKEND_URL", "http://breast-cancer-classification:5555")
AI_TEXT = os.environ.get("AI_TEXT", "PROCESSED BY AI")
AI_COLOR = os.environ.get("AI_COLOR", "red")
AI_NAME = os.environ.get("AI_NAME", "Breast Cancer Classification Model")


def notify_subscriber(workitem, subscriber_url):
    """
    Send UPS notification to a single subscriber (RAD-87)

    Args:
        workitem: UPSWorkitem instance
        subscriber_url: Subscriber's callback URL
    """
    try:
        response = requests.post(
            f"{subscriber_url}/ups-rs/workitems/{workitem.workitem_uid}",
            data=workitem.to_json(),
            headers={"Content-Type": "application/dicom+json"},
            timeout=5
        )
        if response.status_code == 200:
            print(f"Notified subscriber {subscriber_url}: workitem {workitem.workitem_uid} state={workitem.get_state()}")
        else:
            print(f"Notification failed for {subscriber_url}: {response.status_code}")
    except Exception as e:
        print(f"Error notifying {subscriber_url}: {str(e)}")


def notify_all_subscribers(workitem):
    """
    Send UPS notifications to all registered subscribers (RAD-87)

    Args:
        workitem: UPSWorkitem instance
    """
    from ups.subscription_storage import subscription_storage

    subscribers = subscription_storage.get_subscribers(workitem.workitem_uid)

    if not subscribers:
        print(f"No subscribers for workitem {workitem.workitem_uid}")
        return

    print(f"Notifying {len(subscribers)} subscriber(s) for workitem {workitem.workitem_uid}")

    for subscriber_url in subscribers:
        notify_subscriber(workitem, subscriber_url)


def process_workitem(workitem):
    """
    Process a UPS workitem immediately (similar to OnStableStudy pattern)

    Args:
        workitem: UPSWorkitem instance
    """
    print(f"Processing workitem {workitem.workitem_uid}")
    overall_start = time.time()

    try:
        # Step 1: Update state to IN_PROGRESS with initial progress
        workitem.update_state(
            "IN_PROGRESS",
            progress_percent=10,
            progress_description="Starting AI inference"
        )
        ups_storage.store_workitem(workitem)
        notify_all_subscribers(workitem)

        # Step 2: Extract WADO-RS retrieval URLs from workitem
        wado_rs_urls = workitem.get_wado_rs_urls()
        study_uid = workitem.get_study_uid()

        print(f"Workitem has {len(wado_rs_urls)} WADO-RS retrieval URLs")

        # Update: Retrieved metadata
        workitem.update_state(
            "IN_PROGRESS",
            progress_percent=20,
            progress_description="Retrieved study metadata"
        )
        ups_storage.store_workitem(workitem)
        notify_all_subscribers(workitem)

        # Step 3: Call AI model with WADO-RS URLs
        try:
            # Update: Sending data to AI model
            workitem.update_state(
                "IN_PROGRESS",
                progress_percent=30,
                progress_description="Sending data to AI model"
            )
            ups_storage.store_workitem(workitem)
            notify_all_subscribers(workitem)

            step_start = time.time()
            model_response = requests.post(
                f"{MODEL_BACKEND_URL}/analyze/mri",
                json={
                    "wado_rs_retrieval": wado_rs_urls,
                    "study_uid": study_uid
                },
                timeout=1000,
            )
            step_duration = (time.time() - step_start) * 1000
            print(f"TIMING: model_backend_request: {step_duration:.2f}ms")

            # Update: Model processing
            workitem.update_state(
                "IN_PROGRESS",
                progress_percent=50,
                progress_description="AI model analyzing data"
            )
            ups_storage.store_workitem(workitem)
            notify_all_subscribers(workitem)

            if model_response.status_code != 200:
                error_msg = f"Model error: {model_response.status_code} - {model_response.text}"
                print(error_msg)
                workitem.update_state("CANCELED", error_msg)
                ups_storage.store_workitem(workitem)
                notify_all_subscribers(workitem)
                return

            model_results = model_response.json()

        except requests.exceptions.RequestException as e:
            error_msg = f"Network error calling model: {str(e)}"
            print(error_msg)
            workitem.update_state("CANCELED", error_msg)
            ups_storage.store_workitem(workitem)
            notify_all_subscribers(workitem)
            return

        # Step 4: Process results and upload to viewer (import existing SR/SC creation logic)
        try:
            # Import the existing result processing functions from server.py
            from server import (
                detect_response_format,
                create_bilateral_sr,
                create_multiframe_attention_sc
            )

            # Get the first WADO-RS URL to retrieve original DICOM for SR/SC creation
            first_retrieval = wado_rs_urls[0] if wado_rs_urls else None
            if not first_retrieval:
                raise Exception("No retrieval URLs in workitem")

            # Update: Retrieving source images
            workitem.update_state(
                "IN_PROGRESS",
                progress_percent=70,
                progress_description="Retrieving source images"
            )
            ups_storage.store_workitem(workitem)
            notify_all_subscribers(workitem)

            # Retrieve a sample DICOM instance via WADO-RS from viewer (not local storage)
            print(f"Retrieving sample DICOM via WADO-RS from {first_retrieval['retrieval_url']}")

            try:
                wado_response = requests.get(
                    first_retrieval["retrieval_url"],
                    headers={"Accept": "multipart/related; type=application/dicom; transfer-syntax=*"},
                    timeout=60
                )

                if wado_response.status_code != 200:
                    raise Exception(f"WADO-RS retrieval failed: {wado_response.status_code}")

                # Parse multipart response to get first DICOM instance
                content_type = wado_response.headers.get('Content-Type', '')
                boundary = None
                if 'boundary=' in content_type:
                    for part in content_type.split(';'):
                        part = part.strip()
                        if part.startswith('boundary='):
                            boundary = part.split('boundary=')[1].strip().strip('"')
                            break

                if not boundary:
                    raise Exception("No boundary in WADO-RS response")

                # Simple parse: extract first DICOM part
                parts = wado_response.content.split(f'--{boundary}'.encode())
                original_dicom = None

                for part in parts:
                    if b'Content-Type: application/dicom' in part:
                        # Find DICOM data after headers
                        dicom_start = part.find(b'\r\n\r\n')
                        if dicom_start != -1:
                            dicom_data = part[dicom_start+4:].rstrip(b'\r\n-')
                            if len(dicom_data) > 128:
                                original_dicom = dcmread(io.BytesIO(dicom_data))
                                break

                if not original_dicom:
                    raise Exception("No DICOM data found in WADO-RS response")

                print(f"Retrieved sample DICOM via WADO-RS: {original_dicom.SOPInstanceUID}")

            except Exception as e:
                raise Exception(f"Failed to retrieve sample DICOM via WADO-RS: {str(e)}")

            # Update: Creating DICOM results
            workitem.update_state(
                "IN_PROGRESS",
                progress_percent=85,
                progress_description="Creating DICOM results"
            )
            ups_storage.store_workitem(workitem)
            notify_all_subscribers(workitem)

            # Detect response format and create DICOM objects
            response_format = detect_response_format(model_results)
            print(f"Detected response format: {response_format}")

            dicom_objects_to_upload = []
            current_date = datetime.now().strftime("%Y%m%d")
            current_time = datetime.now().strftime("%H%M%S.%f")[:-3]

            if response_format == "bilateral":
                sr_bytes, current_date, current_time, sr_sop_instance_uid = (
                    create_bilateral_sr(original_dicom, model_results)
                )
                dicom_objects_to_upload = [(sr_bytes, "SR-Bilateral")]

            elif response_format == "bilateral_with_heatmap":
                sr_bytes, current_date, current_time, sr_sop_instance_uid = (
                    create_bilateral_sr(original_dicom, model_results)
                )
                dicom_objects_to_upload.append((sr_bytes, "SR-Bilateral-MST"))

                # Create multi-frame SC with attention maps
                attention_maps = model_results.get("attention_maps", {})
                if attention_maps and attention_maps.get("data"):
                    # Need first instance with proper spatial metadata
                    sc_bytes = create_multiframe_attention_sc(
                        original_dicom,
                        attention_maps,
                        creation_date=current_date,
                        creation_time=current_time,
                        sr_sop_instance_uid=sr_sop_instance_uid,
                        slice_spacing=1.0  # Would need to extract from DICOM
                    )
                    dicom_objects_to_upload.append((sc_bytes, "SC-MultiFrame"))

            # Step 5: Upload results to viewer
            # Update: Uploading results
            workitem.update_state(
                "IN_PROGRESS",
                progress_percent=95,
                progress_description="Uploading results to viewer"
            )
            ups_storage.store_workitem(workitem)
            notify_all_subscribers(workitem)

            upload_start = time.time()
            for dicom_bytes, desc in dicom_objects_to_upload:
                upload_item_start = time.time()
                response = requests.post(
                    "http://orthanc-viewer:8042/instances",
                    data=dicom_bytes,
                    headers={"Content-Type": "application/dicom"},
                    timeout=10,
                )
                upload_item_duration = (time.time() - upload_item_start) * 1000
                print(f"TIMING: upload_{desc}: {upload_item_duration:.2f}ms")

                if response.status_code == 200:
                    print(f"AI {desc} uploaded to viewer")
                else:
                    print(f"Failed to upload {desc}: {response.status_code}")

            upload_duration = (time.time() - upload_start) * 1000
            print(f"TIMING: upload_all_to_viewer: {upload_duration:.2f}ms")

        except Exception as e:
            error_msg = f"Error processing results: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            workitem.update_state("CANCELED", error_msg)
            ups_storage.store_workitem(workitem)
            notify_all_subscribers(workitem)
            return

        # Step 6: Complete workitem
        workitem.update_state("COMPLETED", "AI inference completed successfully")
        ups_storage.store_workitem(workitem)
        notify_all_subscribers(workitem)

        overall_duration = (time.time() - overall_start) * 1000
        print(f"TIMING: total_workitem_processing: {overall_duration:.2f}ms")
        print(f"Successfully processed workitem {workitem.workitem_uid}")

    except Exception as e:
        error_msg = f"Unexpected error processing workitem: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        try:
            workitem.update_state("CANCELED", error_msg)
            ups_storage.store_workitem(workitem)
        except:
            pass  # Best effort state update
