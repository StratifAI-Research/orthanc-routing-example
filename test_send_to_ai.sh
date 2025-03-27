#!/bin/bash

# Configuration
ORTHANC_URL="http://localhost:8000"
DICOM_FILE="./sample_data/blue-circle.dcm"  # Replace with actual DICOM file path
TARGET_SERVER="ai-server"
TARGET_URL="http://orthanc-ai:8042"  # Replace with actual AI server URL

# Step 1: Upload DICOM file to Orthanc
echo "Uploading DICOM file..."
RESPONSE=$(curl -s -X POST "$ORTHANC_URL/instances" \
    --data-binary @"$DICOM_FILE")

# Extract StudyID from response
STUDY_ID=$(echo $RESPONSE | jq -r '.ParentStudy')

if [ -z "$STUDY_ID" ]; then
    echo "Failed to get study ID"
    exit 1
fi

echo "Uploaded study ID: $STUDY_ID"

# Step 2: Call the send-to-ai endpoint with target server info
echo "Sending study to AI..."
curl -X POST "$ORTHANC_URL/send-to-ai" \
    -H "Content-Type: application/json" \
    -d "{
        \"study_id\": \"$STUDY_ID\",
        \"target\": \"$TARGET_SERVER\",
        \"target_url\": \"$TARGET_URL\"
    }"

echo -e "\nDone!" 