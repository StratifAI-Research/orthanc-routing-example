import datetime
import io
import json
import os
from datetime import datetime
import base64

import numpy as np
import orthanc
import requests
from PIL import Image, ImageDraw, ImageFont
from pydicom import Dataset, FileDataset, dcmread
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import (
    ComprehensiveSRStorage,
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
)

# Configuration
MODEL_BACKEND_URL = os.environ.get(
    "MODEL_BACKEND_URL", "http://breast-cancer-classification:5555"
)
AI_TEXT = os.environ.get("AI_TEXT", "PROCESSED BY AI")
AI_COLOR = os.environ.get("AI_COLOR", "red")
AI_NAME = os.environ.get("AI_NAME", "Breast Cancer Classification Model")


def add_text_overlay(pixel_array, text="PROCESSED BY AI", color="red"):
    """
    Adds a large text overlay to the pixel array with the specified color.
    Handles multi-frame (4D) and single-frame (2D/3D) DICOM.
    """
    # Handle multi-frame DICOM (4D array: frames, height, width, channels)
    if len(pixel_array.shape) == 4:
        processed_frames = []
        for frame in pixel_array:
            im = Image.fromarray(frame)
            draw = ImageDraw.Draw(im)

            # Load font
            try:
                font = ImageFont.truetype("arial.ttf", size=50)
            except IOError:
                font = ImageFont.load_default()

            # Calculate text position using textbbox
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            position = ((im.width - text_width) // 2, (im.height - text_height) // 2)

            # Add overlay with specified color
            draw.text(position, text, fill=color, font=font)
            processed_frames.append(np.array(im))

        return np.stack(processed_frames)

    # Handle single-frame DICOM
    else:
        if len(pixel_array.shape) == 2:
            im = Image.fromarray(pixel_array).convert("RGB")
        else:
            im = Image.fromarray(pixel_array)

        draw = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("arial.ttf", size=50)
        except IOError:
            font = ImageFont.load_default()

        # Calculate text position using textbbox
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        position = ((im.width - text_width) // 2, (im.height - text_height) // 2)

        # Add overlay with specified color
        draw.text(position, text, fill=color, font=font)
        return np.array(im)




def create_multiframe_attention_sc(
    original_dicom,
    attention_maps,
    creation_date=None,
    creation_time=None,
    sr_sop_instance_uid=None,
):
    """
    Create multi-frame DICOM Secondary Capture for complete attention heatmap volume

    Args:
        original_dicom: Original DICOM dataset
        attention_maps: Dict with 'data' (base64 encoded bytes), 'shape', and 'dtype' keys
                       Contains ALL RGB overlay slices as base64-encoded numpy array
        creation_date: Instance creation date
        creation_time: Instance creation time
        sr_sop_instance_uid: Reference to SR document

    Returns:
        DICOM bytes containing complete 3D RGB overlay heatmap as multi-frame SC
    """
    ds = Dataset()
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta

    # Copy metadata from original
    for tag in [
        "PatientName",
        "PatientID",
        "PatientBirthDate",
        "PatientSex",
        "StudyInstanceUID",
        "StudyDate",
        "StudyTime",
        "StudyID",
    ]:
        setattr(ds, tag, getattr(original_dicom, tag, None))

    # Set derived attributes
    ds.Modality = "SC"
    ds.SeriesInstanceUID = generate_uid()
    ds.ConversionType = "DF"
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = generate_uid()

    # Multi-frame attention heatmap description
    ds.StudyDescription = "AI Attention Heatmap Visualization"
    ds.SeriesDescription = f"{AI_NAME} - Complete 3D Attention Heatmap"

    # Add AI model metadata
    ds.ManufacturerModelName = AI_NAME

    # Use provided timestamps
    if creation_date and creation_time:
        ds.InstanceCreationDate = creation_date
        ds.InstanceCreationTime = creation_time
    else:
        ds.InstanceCreationDate = datetime.now().strftime("%Y%m%d")
        ds.InstanceCreationTime = datetime.now().strftime("%H%M%S.%f")[:-3]

    # Decode base64 RGB overlay data from MST model (already uint8, already blended)
    overlay_b64 = attention_maps.get('data')
    overlay_shape = tuple(attention_maps.get('shape'))  # [num_frames, rows, cols, 3]

    print(f"Decoding base64 overlay data with shape: {overlay_shape}")

    # Decode base64 and reshape to original array
    overlay_bytes = base64.b64decode(overlay_b64)
    stacked_frames = np.frombuffer(overlay_bytes, dtype=np.uint8).reshape(overlay_shape)

    print(f"Decoded overlay shape: {stacked_frames.shape}")

    # Set multi-frame attributes
    num_frames = stacked_frames.shape[0]
    ds.NumberOfFrames = num_frames

    # Set image dimensions: stacked_frames is [num_frames, rows, cols, 3]
    ds.Rows, ds.Columns, ds.SamplesPerPixel = stacked_frames.shape[1:]

    # Set pixel data attributes
    ds.PhotometricInterpretation = "RGB"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PlanarConfiguration = 0

    # Convert stacked frames to bytes
    ds.PixelData = stacked_frames.tobytes()

    # Add reference to original image
    ref_image_sequence = Sequence()
    ref_image = Dataset()
    ref_image.ReferencedSOPClassUID = original_dicom.SOPClassUID
    ref_image.ReferencedSOPInstanceUID = original_dicom.SOPInstanceUID
    ref_image_sequence.append(ref_image)
    ds.ReferencedImageSequence = ref_image_sequence

    # Add reference to SR if provided
    if sr_sop_instance_uid:
        ref_instance_sequence = Sequence()
        ref_instance = Dataset()
        ref_instance.ReferencedSOPClassUID = ComprehensiveSRStorage
        ref_instance.ReferencedSOPInstanceUID = sr_sop_instance_uid
        ref_instance_sequence.append(ref_instance)
        ds.ReferencedInstanceSequence = ref_instance_sequence

    # Write to buffer
    buffer = io.BytesIO()
    ds.save_as(buffer)
    return buffer.getvalue()



def create_text_overlay_sc(
    original_dicom,
    text="PROCESSED BY AI",
    color="red",
    creation_date=None,
    creation_time=None,
    model_results=None,
    sr_sop_instance_uid=None,
):
    """Creates DICOM SC with text overlay for bilateral classification results"""
    ds = Dataset()
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta

    # Copy metadata
    for tag in [
        "PatientName",
        "PatientID",
        "PatientBirthDate",
        "PatientSex",
        "StudyInstanceUID",
        "StudyDate",
        "StudyTime",
        "StudyID",
    ]:
        setattr(ds, tag, getattr(original_dicom, tag, None))

    # Set derived attributes
    ds.Modality = "SC"
    ds.SeriesInstanceUID = generate_uid()
    ds.ConversionType = "DF"
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = generate_uid()

    # AI-specific descriptions
    ds.StudyDescription = "AI Heatmap Visualization"
    ds.SeriesDescription = f"{AI_NAME} - Heatmap"

    # Add AI model metadata to EXACTLY match SR content
    ds.ManufacturerModelName = AI_NAME  # Keep this for basic DICOM compliance

    # Add the SAME structured content as SR for proper grouping
    # This mimics the SR ContentSequence structure in SC format
    content_sequence = Sequence()

    # Model metadata item matching SR exactly
    model_metadata = Dataset()
    model_metadata.ValueType = "CODE"
    model_metadata.ConceptNameCodeSequence = [
        create_code_sequence(
            code_value="12710003",  # SAME as SR
            coding_scheme="SCT",  # SAME as SR
            code_meaning="AI Model",  # SAME as SR
        )
    ]
    model_metadata.TextValue = AI_NAME  # SAME as SR
    model_metadata.AlgorithmName = "ResNet-50"  # SAME as SR
    model_metadata.AlgorithmVersion = "1.2.3"  # SAME as SR

    content_sequence.append(model_metadata)
    ds.ContentSequence = content_sequence

    # Use provided timestamps for SR-SC matching, or generate new ones
    if creation_date and creation_time:
        ds.InstanceCreationDate = creation_date
        ds.InstanceCreationTime = creation_time
    else:
        ds.InstanceCreationDate = datetime.now().strftime("%Y%m%d")
        ds.InstanceCreationTime = datetime.now().strftime("%H%M%S.%f")[:-3]

    # Process pixel data
    pixel_array = original_dicom.pixel_array
    processed_pixel_array = add_text_overlay(pixel_array, text, color)

    # Handle different array dimensions
    if len(processed_pixel_array.shape) == 4:
        ds.NumberOfFrames = processed_pixel_array.shape[0]
        ds.Rows = processed_pixel_array.shape[1]
        ds.Columns = processed_pixel_array.shape[2]
        ds.SamplesPerPixel = processed_pixel_array.shape[3]
    else:
        ds.Rows, ds.Columns, ds.SamplesPerPixel = processed_pixel_array.shape

    # Set pixel data attributes
    ds.PhotometricInterpretation = "RGB"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PlanarConfiguration = 0
    ds.PixelData = processed_pixel_array.tobytes()

    # Add reference to original image
    ref_image_sequence = Sequence()
    ref_image = Dataset()
    ref_image.ReferencedSOPClassUID = original_dicom.SOPClassUID
    ref_image.ReferencedSOPInstanceUID = original_dicom.SOPInstanceUID
    ref_image_sequence.append(ref_image)
    ds.ReferencedImageSequence = ref_image_sequence

    # Add reference to corresponding SR if provided
    if sr_sop_instance_uid:
        ref_instance_sequence = Sequence()
        ref_instance = Dataset()
        ref_instance.ReferencedSOPClassUID = ComprehensiveSRStorage
        ref_instance.ReferencedSOPInstanceUID = sr_sop_instance_uid
        ref_instance_sequence.append(ref_instance)
        ds.ReferencedInstanceSequence = ref_instance_sequence

    # Write to in-memory buffer
    buffer = io.BytesIO()
    ds.save_as(buffer)
    return buffer.getvalue()


def create_code_sequence(code_value, coding_scheme, code_meaning):
    """Helper to create coded entries"""
    code_seq = Dataset()
    code_seq.CodeValue = code_value
    code_seq.CodingSchemeDesignator = coding_scheme
    code_seq.CodeMeaning = code_meaning
    return code_seq


def create_measurement(value, unit, code_value, coding_scheme):
    """Helper for numeric measurements"""
    measurement = Dataset()
    measurement.NumericValue = value
    measurement.MeasurementUnitsCodeSequence = [
        create_code_sequence(
            code_value=code_value, coding_scheme=coding_scheme, code_meaning=unit
        )
    ]
    return measurement


def create_mst_sr(original_ds, model_results):
    """
    Create DICOM Structured Report (SR) for MST model results

    DEPRECATED: MST models now use bilateral format. Use create_bilateral_sr instead.

    Args:
        original_ds: Original DICOM dataset
        model_results: Dict with 'classification' and 'attention_maps' keys

    Returns:
        Tuple of (sr_bytes, creation_date, creation_time, sop_instance_uid)
    """
    classification = model_results.get("classification", {})

    # File meta info
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = ComprehensiveSRStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)

    # Basic patient/study identification
    ds.PatientName = original_ds.PatientName
    ds.PatientID = original_ds.PatientID
    ds.StudyInstanceUID = original_ds.StudyInstanceUID
    ds.SeriesInstanceUID = generate_uid()
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID

    # SR-specific attributes
    ds.Modality = "SR"
    ds.SOPClassUID = ComprehensiveSRStorage
    ds.StudyDescription = "AI Classification Report - MST"
    ds.SeriesDescription = "MST Attention-Based Classification"

    # Timestamps
    current_date = datetime.now().strftime("%Y%m%d")
    current_time = datetime.now().strftime("%H%M%S.%f")[:-3]
    ds.InstanceCreationDate = current_date
    ds.InstanceCreationTime = current_time

    # Create content sequence
    content_sequence = Sequence()

    # Root container
    root_container = Dataset()
    root_container.ValueType = "CONTAINER"
    root_container.ConceptNameCodeSequence = [
        create_code_sequence(
            code_value="18748-4",
            coding_scheme="LN",
            code_meaning="Diagnostic Imaging Report",
        )
    ]
    root_container.ContinuityOfContent = "SEPARATE"

    content_items = []

    # Classification result
    if classification:
        prediction_item = Dataset()
        prediction_item.ValueType = "CODE"
        prediction_item.ConceptNameCodeSequence = [
            create_code_sequence(
                code_value="R-00339",
                coding_scheme="SRT",
                code_meaning="Classification Result",
            )
        ]

        is_malignant = classification.get("prediction") == "Malignant"
        prediction_item.ConceptCodeSequence = [
            create_code_sequence(
                code_value="86049000" if is_malignant else "108369006",
                coding_scheme="SCT",
                code_meaning="Malignant" if is_malignant else "Benign",
            )
        ]

        probability = classification.get("probability", 0)
        prediction_item.MeasuredValueSequence = [
            create_measurement(
                value=probability * 100,
                unit="%",
                code_value="%",
                coding_scheme="UCUM",
            )
        ]
        content_items.append(prediction_item)

    # Model metadata
    model_metadata = Dataset()
    model_metadata.ValueType = "CODE"
    model_metadata.ConceptNameCodeSequence = [
        create_code_sequence(
            code_value="12710003",
            coding_scheme="SCT",
            code_meaning="AI Model",
        )
    ]
    model_metadata.TextValue = classification.get("model_name", "MST")
    model_metadata.AlgorithmName = classification.get("architecture", "Vision Transformer")
    model_metadata.AlgorithmVersion = classification.get("version", "1.0")
    content_items.append(model_metadata)

    # Assemble structure
    root_container.ContentSequence = content_items
    content_sequence.append(root_container)
    ds.ContentSequence = content_sequence

    # Referenced images
    ref_image_sequence = Sequence()
    ref_image = Dataset()
    ref_image.ReferencedSOPClassUID = original_ds.SOPClassUID
    ref_image.ReferencedSOPInstanceUID = original_ds.SOPInstanceUID
    ref_image_sequence.append(ref_image)
    ds.ReferencedImageSequence = ref_image_sequence

    # Write to buffer
    buffer = io.BytesIO()
    ds.save_as(buffer)
    return buffer.getvalue(), current_date, current_time, ds.SOPInstanceUID


def create_bilateral_sr(original_ds, model_results):
    """Create DICOM Structured Report (SR) for bilateral classification model results in memory"""
    # File meta info
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = ComprehensiveSRStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)

    # Basic patient/study identification (link to original study)
    ds.PatientName = original_ds.PatientName
    ds.PatientID = original_ds.PatientID
    ds.StudyInstanceUID = original_ds.StudyInstanceUID
    ds.SeriesInstanceUID = generate_uid()  # New UID for SR series
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID

    # SR-specific attributes
    ds.Modality = "SR"
    ds.SOPClassUID = ComprehensiveSRStorage
    ds.StudyDescription = "AI Classification Report"
    ds.SeriesDescription = "Automated Diagnostic Findings"

    # Use consistent timestamps for SR-SC matching
    current_date = datetime.now().strftime("%Y%m%d")
    current_time = datetime.now().strftime("%H%M%S.%f")[:-3]  # Include milliseconds
    ds.InstanceCreationDate = current_date
    ds.InstanceCreationTime = current_time

    # Create content sequence for structured reporting
    content_sequence = Sequence()

    # Root container
    root_container = Dataset()
    root_container.ValueType = "CONTAINER"
    root_container.ConceptNameCodeSequence = [
        create_code_sequence(
            code_value="18748-4",  # LOINC code for Diagnostic Imaging Report
            coding_scheme="LN",
            code_meaning="Diagnostic Imaging Report",
        )
    ]
    root_container.ContinuityOfContent = "SEPARATE"

    # 2. Classification results for both sides
    content_items = []

    for side in ["left", "right"]:
        if side in model_results and "error" not in model_results[side]:
            finding_item = Dataset()
            finding_item.ValueType = "CODE"
            finding_item.ConceptNameCodeSequence = [
                create_code_sequence(
                    code_value="R-00339",  # SNOMED CT Observable Entity
                    coding_scheme="SRT",
                    code_meaning=f"{side.capitalize()} Side Probability",
                )
            ]

            # Map "Cancerous" to malignant and "Not Cancerous" to benign
            is_malignant = model_results[side]["prediction"] == "Cancerous"
            finding_item.ConceptCodeSequence = [
                create_code_sequence(
                    code_value="86049000" if is_malignant else "108369006",
                    coding_scheme="SCT",
                    code_meaning="Malignant" if is_malignant else "Benign",
                )
            ]

            finding_item.MeasuredValueSequence = [
                create_measurement(
                    value=model_results[side]["confidence"],
                    unit="%",
                    code_value="%",
                    coding_scheme="UCUM",
                )
            ]

            content_items.append(finding_item)
        else:
            # Add error message if available
            error_item = Dataset()
            error_item.ValueType = "TEXT"
            error_item.ConceptNameCodeSequence = [
                create_code_sequence(
                    code_value="R-00339",
                    coding_scheme="SRT",
                    code_meaning=f"{side.capitalize()} Side Analysis",
                )
            ]
            error_item.TextValue = model_results[side].get("error", "Analysis failed")
            content_items.append(error_item)

    # 3. AI Model metadata
    model_metadata_item = Dataset()
    model_metadata_item.ValueType = "CODE"
    model_metadata_item.ConceptNameCodeSequence = [
        create_code_sequence(
            code_value="12710003",  # SCT code for "Algorithm"
            coding_scheme="SCT",
            code_meaning="AI Model",
        )
    ]

    # Use model_metadata from model results if available (MST format)
    model_meta = model_results.get("model_metadata", {})
    if model_meta:
        model_metadata_item.TextValue = model_meta.get("model_name", AI_NAME)
        model_metadata_item.AlgorithmName = model_meta.get("architecture", "Unknown")
        model_metadata_item.AlgorithmVersion = model_meta.get("version", "Unknown")
    else:
        # Fallback to defaults for basic bilateral models
        model_metadata_item.TextValue = AI_NAME
        model_metadata_item.AlgorithmName = "ResNet-50"
        model_metadata_item.AlgorithmVersion = "1.2.3"

    # Assemble the structure
    content_items.append(model_metadata_item)
    root_container.ContentSequence = content_items
    content_sequence.append(root_container)
    ds.ContentSequence = content_sequence

    # Referenced images (link to original study)
    ref_image_sequence = Sequence()
    ref_image = Dataset()
    ref_image.ReferencedSOPClassUID = original_ds.SOPClassUID
    ref_image.ReferencedSOPInstanceUID = original_ds.SOPInstanceUID
    ref_image_sequence.append(ref_image)
    ds.ReferencedImageSequence = ref_image_sequence

    # Write to in-memory buffer
    buffer = io.BytesIO()
    ds.save_as(buffer)
    return buffer.getvalue(), current_date, current_time, ds.SOPInstanceUID


def detect_response_format(model_results):
    """
    Detect the format of AI model response

    Returns:
        "bilateral" - for basic bilateral models returning {left: {...}, right: {...}}
        "bilateral_with_heatmap" - for MST-like models returning {left: {...}, right: {...}, attention_maps: [...]}
    """
    has_bilateral = "left" in model_results or "right" in model_results
    has_attention_maps = "attention_maps" in model_results

    if has_bilateral and has_attention_maps:
        return "bilateral_with_heatmap"
    elif has_bilateral:
        return "bilateral"
    else:
        raise ValueError(f"Unknown response format. Keys: {list(model_results.keys())}")


def OnStableStudy(changeType, level, resourceId):
    if changeType == orthanc.ChangeType.STABLE_STUDY:
        print(f"Processing stable study: {resourceId}")

        try:
            # Get study instances
            instances = json.loads(
                orthanc.RestApiGet(f"/studies/{resourceId}/instances")
            )
            if not instances:
                print(f"No instances in study {resourceId}")
                return

            # Process first instance
            instance_id = instances[0]["ID"]
            dicom_buffer = orthanc.GetDicomForInstance(instance_id)
            original_dicom = dcmread(io.BytesIO(dicom_buffer))

            # Get series instance UID
            series_instance_uid = original_dicom.SeriesInstanceUID

            # Call the model backend
            try:
                model_response = requests.post(
                    f"{MODEL_BACKEND_URL}/analyze/mri",
                    json={"seriesInstanceUID": series_instance_uid},
                    timeout=1000,
                )

                if model_response.status_code != 200:
                    print(
                        f"Error from model backend: {model_response.status_code} - {model_response.text}"
                    )
                    return

                model_results = model_response.json()

                # Detect response format and process accordingly
                response_format = detect_response_format(model_results)
                print(f"Detected response format: {response_format}")

                dicom_objects_to_upload = []

                if response_format == "bilateral":
                    # Process basic bilateral classification results (no heatmap)
                    sr_bytes, current_date, current_time, sr_sop_instance_uid = (
                        create_bilateral_sr(original_dicom, model_results)
                    )
                    sc_bytes = create_text_overlay_sc(
                        original_dicom,
                        AI_TEXT,
                        AI_COLOR,
                        current_date,
                        current_time,
                        model_results,
                        sr_sop_instance_uid,
                    )
                    dicom_objects_to_upload = [(sc_bytes, "SC-Text"), (sr_bytes, "SR-Bilateral")]

                elif response_format == "bilateral_with_heatmap":
                    # Process bilateral classification with RGB overlay heatmaps (MST model)
                    print(f"Processing bilateral classification with RGB overlay heatmaps")

                    sr_bytes, current_date, current_time, sr_sop_instance_uid = (
                        create_bilateral_sr(original_dicom, model_results)
                    )
                    dicom_objects_to_upload.append((sr_bytes, "SR-Bilateral-MST"))

                    # Create single multi-frame SC with RGB overlays from tensor_cam2image
                    attention_maps = model_results.get("attention_maps", {})
                    num_frames = attention_maps.get("shape", [0])[0] if attention_maps else 0
                    print(f"Received base64-encoded RGB overlay data with {num_frames} frames")

                    if attention_maps and attention_maps.get("data"):
                        sc_bytes = create_multiframe_attention_sc(
                            original_dicom,
                            attention_maps,
                            creation_date=current_date,
                            creation_time=current_time,
                            sr_sop_instance_uid=sr_sop_instance_uid,
                        )
                        dicom_objects_to_upload.append((sc_bytes, "SC-MultiFrame-RGB-Overlay"))
                        print(f"Multi-frame SC created with {num_frames} RGB overlay frames")
                    else:
                        print("WARNING: No attention maps found in model results")

                # Upload all DICOM objects to orthanc-viewer
                for dicom_bytes, desc in dicom_objects_to_upload:
                    response = requests.post(
                        "http://orthanc-viewer:8042/instances",
                        data=dicom_bytes,
                        headers={"Content-Type": "application/dicom"},
                        timeout=10,
                    )

                    if response.status_code == 200:
                        print(
                            f"AI {desc} response successfully stored in orthanc-viewer"
                        )
                    else:
                        print(
                            f"Failed to store AI {desc} response in orthanc-viewer: {response.status_code}"
                        )
                        print(
                            f"Response content: {response.text[:200]}"
                        )  # Truncated for logs

            except requests.exceptions.RequestException as e:
                print(f"Network error calling model backend: {str(e)}")
            except Exception as e:
                print(f"Error processing model results: {str(e)}")
                import traceback
                traceback.print_exc()

        except Exception as e:
            print(f"Error processing study {resourceId}: {str(e)}")
            import traceback
            traceback.print_exc()


# Register the callback function
orthanc.RegisterOnChangeCallback(OnStableStudy)
