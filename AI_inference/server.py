import uuid

import numpy as np
import orthanc
import requests
from PIL import Image
from pydicom import dcmread
from pydicom._storage_sopclass_uids import SecondaryCaptureImageStorage
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid


def create_mock_ai_response(original_dicom_path, output_path):
    """
    Creates a mock AI response DICOM file based on the original DICOM file.
    """
    # Load the original DICOM file
    original_dicom = dcmread(original_dicom_path)

    # Create a new DICOM dataset
    ds = Dataset()
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta

    # Copy metadata from the original DICOM
    ds.PatientName = original_dicom.PatientName
    ds.PatientID = original_dicom.PatientID
    ds.PatientBirthDate = original_dicom.PatientBirthDate
    ds.PatientSex = original_dicom.PatientSex
    ds.StudyInstanceUID = original_dicom.StudyInstanceUID
    ds.StudyDate = original_dicom.StudyDate
    ds.StudyTime = original_dicom.StudyTime
    ds.ReferringPhysicianName = None
    ds.StudyID = original_dicom.StudyID
    ds.AccessionNumber = None

    # Add new data for the mock AI response
    ds.Modality = "SC"  # Secondary Capture
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber = None
    ds.ConversionType = "DF"  # Derived from original
    ds.InstanceNumber = None

    # Add a mock image (e.g., a placeholder image)
    im = Image.open("sample_data/image.png")  # Replace with your mock image
    arr = np.asarray(im)
    arr = arr[:, :, :3]  # Remove alpha channel if present
    arr = np.stack((arr, arr))  # Create multiple frames
    ds.NumberOfFrames, ds.Rows, ds.Columns, ds.SamplesPerPixel = arr.shape
    ds.PhotometricInterpretation = "RGB"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PlanarConfiguration = 0
    ds.PixelData = arr.tobytes()

    # Set SOP Class and Instance UIDs
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = generate_uid()

    # Save the mock AI response as a new DICOM file
    ds.save_as(output_path, write_like_original=False)

def SendAIResult(changeType, level, resourceId):
    """
    Callback function triggered when a study becomes stable.
    Creates a mock AI response and sends it back to the orthanc-viewer instance.
    """
    if changeType == orthanc.ChangeType.STABLE_STUDY:
        print(f"Stable study: {resourceId}")

        # Download the original study from Orthanc
        original_dicom_path = f"/tmp/{resourceId}.dcm"
        with open(original_dicom_path, "wb") as f:
            f.write(orthanc.RestApiGet(f"/studies/{resourceId}/archive"))

        # Create a mock AI response
        mock_response_path = f"/tmp/mock_ai_{resourceId}.dcm"
        create_mock_ai_response(original_dicom_path, mock_response_path)

        # Send the mock AI response back to the orthanc-viewer instance
        with open(mock_response_path, "rb") as f:
            response = requests.post(
                url="http://orthanc-viewer:8042/instances",
                data=f.read(),
                headers={"Content-Type": "application/dicom"}
            )

        if response.status_code == 200:
            print(f"Mock AI response sent successfully for study {resourceId}")
        else:
            print(f"Failed to send mock AI response for study {resourceId}: {response.status_code}")

# Register the callback function
orthanc.RegisterOnChangeCallback(SendAIResult)