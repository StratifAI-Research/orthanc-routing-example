import io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from pydicom import Dataset, FileMetaDataset, FileDataset
from pydicom.sequence import Sequence
from pydicom.uid import (
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
    ComprehensiveSRStorage
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
    processed_pixel_array = add_text_overlay(pixel_array)

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
    measurement.MeasurementUnitsCodeSequence = [create_code_sequence(
        code_value=code_value,
        coding_scheme=coding_scheme,
        code_meaning=unit
    )]
    return measurement

def create_sr_report(original_ds, classification_result):
    """Create DICOM Structured Report (SR) for classification results in memory"""
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
    ds.Modality = 'SR'
    ds.SOPClassUID = ComprehensiveSRStorage
    ds.StudyDescription = "AI Classification Report"
    ds.SeriesDescription = "Automated Diagnostic Findings"
    ds.InstanceCreationDate = datetime.now().strftime('%Y%m%d')
    ds.InstanceCreationTime = datetime.now().strftime('%H%M%S')

    # Create content sequence for structured reporting
    content_sequence = Sequence()

    # 1. Root container
    root_container = Dataset()
    root_container.ValueType = 'CONTAINER'
    root_container.ConceptNameCodeSequence = [create_code_sequence(
        code_value='18748-4',  # LOINC code for Diagnostic Imaging Report
        coding_scheme='LN',
        code_meaning='Diagnostic Imaging Report'
    )]
    root_container.ContinuityOfContent = 'SEPARATE'

    # 2. Classification result
    finding_item = Dataset()
    finding_item.ValueType = 'CODE'
    finding_item.ConceptNameCodeSequence = [create_code_sequence(
        code_value='R-00339',  # SNOMED CT Observable Entity
        coding_scheme='SRT',
        code_meaning='Probability'
    )]
    finding_item.ConceptCodeSequence = [create_code_sequence(
        code_value='108369006' if classification_result['benign'] else '86049000',
        coding_scheme='SCT',
        code_meaning='Benign' if classification_result['benign'] else 'Malignant'
    )]
    finding_item.MeasuredValueSequence = [create_measurement(
        value=classification_result['confidence'],
        unit='%',
        code_value='%',
        coding_scheme='UCUM'
    )]

    # 3. AI Model metadata
    model_metadata = Dataset()
    model_metadata.ValueType = 'CODE'
    model_metadata.ConceptNameCodeSequence = [create_code_sequence(
        code_value='12710003',  # SCT code for "Algorithm"
        coding_scheme='SCT',
        code_meaning='AI Model'
    )]
    model_metadata.TextValue = "Classification Model v1.0"
    model_metadata.AlgorithmName = "ResNet-50"
    model_metadata.AlgorithmVersion = "1.2.3"

    # Assemble the structure
    root_container.ContentSequence = [finding_item, model_metadata]
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
    return buffer.getvalue()

# Example classification result structure
MOCK_CLASSIFICATION = {
    'benign': True,
    'confidence': 95.7,
    'model_version': '1.0'
} 