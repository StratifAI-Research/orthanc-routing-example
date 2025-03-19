import io
import json

import numpy as np
import orthanc
import requests
from PIL import Image, ImageDraw, ImageFont
from pydicom import dcmread
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
)


def add_text_overlay(pixel_array, text="PROCESSED BY AI"):
    """
    Adds a large red text overlay to the pixel array.
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

            # Add overlay
            draw.text(position, text, fill="red", font=font)
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

        draw.text(position, text, fill="red", font=font)
        return np.array(im)


def create_mock_ai_dicom(original_dicom):
    """Creates mock AI DICOM dataset in memory"""
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

    # Process pixel data
    pixel_array = original_dicom.pixel_array
    processed_pixel_array = add_text_overlay(pixel_array)  # Correct variable name

    # Handle different array dimensions
    if len(processed_pixel_array.shape) == 4:  # Use correct variable name
        ds.NumberOfFrames = processed_pixel_array.shape[0]
        ds.Rows = processed_pixel_array.shape[1]
        ds.Columns = processed_pixel_array.shape[2]
        ds.SamplesPerPixel = processed_pixel_array.shape[3]
    else:
        ds.Rows, ds.Columns, ds.SamplesPerPixel = (
            processed_pixel_array.shape
        )  # Correct name

    # Set pixel data attributes
    ds.PhotometricInterpretation = "RGB"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PlanarConfiguration = 0
    ds.PixelData = processed_pixel_array.tobytes()  # Correct name

    # Write to in-memory buffer
    buffer = io.BytesIO()
    ds.save_as(buffer)
    return buffer.getvalue()


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

            # Generate and send AI response
            mock_dicom_bytes = create_mock_ai_dicom(original_dicom)

            # Use direct requests call
            response = requests.post(
                "http://orthanc-viewer:8042/instances",
                data=mock_dicom_bytes,
                headers={"Content-Type": "application/dicom"},
                timeout=10,
            )

            # Simplified status check
            if response.status_code == 200:
                print(
                    f"AI response successfully stored (Status: {response.status_code})"
                )
            else:
                print(f"Failed to store AI response (Status: {response.status_code})")
                print(f"Response content: {response.text[:200]}")  # Truncated for logs

        except requests.exceptions.RequestException as e:
            print(f"Network error processing study {resourceId}: {str(e)}")
        except Exception as e:
            print(f"General error processing study {resourceId}: {str(e)}")


# Register the callback function
orthanc.RegisterOnChangeCallback(OnStableStudy)
