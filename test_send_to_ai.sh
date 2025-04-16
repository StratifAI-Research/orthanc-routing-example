#!/bin/bash

# Configuration
ORTHANC_URL="http://localhost:8000"
DICOM_FILE="./sample_data/blue-circle.dcm"
TARGET_SERVER="ai"
TARGET_URL="orthanc-ai:4242/ORTHANC"
DICOMWEB_URL="http://orthanc-ai:8042"

# Default verbosity is off
VERBOSE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -v|--verbose)
      VERBOSE=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [-v|--verbose]"
      exit 1
      ;;
  esac
done

# Set curl verbosity flag
CURL_VERBOSE=""
if [ "$VERBOSE" = true ]; then
  CURL_VERBOSE="-v"
  echo "Verbose mode enabled"
fi

# Upload DICOM file to Orthanc
echo "Uploading DICOM file to Orthanc..."
UPLOAD_RESPONSE=$(curl $CURL_VERBOSE -s -X POST "${ORTHANC_URL}/instances" --data-binary "@${DICOM_FILE}")
STUDY_ID=$(echo "$UPLOAD_RESPONSE" | jq -r '.ParentStudy')

if [ -z "$STUDY_ID" ] || [ "$STUDY_ID" = "null" ]; then
    echo "Error: Failed to get ParentStudy from upload response"
    exit 1
fi

echo "Study ID: $STUDY_ID"

# Test DICOM endpoint
echo "Testing send-to-ai-dicom endpoint..."
curl $CURL_VERBOSE -X POST "${ORTHANC_URL}/send-to-ai-dicom" \
    -H "Content-Type: application/json" \
    -d "{\"study_id\":\"$STUDY_ID\",\"target\":\"$TARGET_SERVER\",\"target_url\":\"$TARGET_URL\"}"

# Test DICOMWeb endpoint
echo "Testing send-to-ai-dicomweb endpoint..."
curl $CURL_VERBOSE -X POST "${ORTHANC_URL}/send-to-ai-dicomweb" \
    -H "Content-Type: application/json" \
    -d "{\"study_id\":\"$STUDY_ID\",\"target\":\"$TARGET_SERVER\",\"target_url\":\"$DICOMWEB_URL\"}"

# Test legacy endpoint
echo "Testing send-to-ai endpoint..."
curl $CURL_VERBOSE -X POST "${ORTHANC_URL}/send-to-ai" \
    -H "Content-Type: application/json" \
    -d "{\"study_id\":\"$STUDY_ID\",\"target\":\"$TARGET_SERVER\",\"target_url\":\"$DICOMWEB_URL\"}"

echo "Test completed" 