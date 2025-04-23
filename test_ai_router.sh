#!/bin/bash

# Configuration
ROUTER_URL="http://localhost:8003"  # Using port 8003 for orthanc-ai-router
VIEWER_URL="http://localhost:8000"  # Using port 8000 for orthanc-viewer
DICOM_DIR="./sample_data/mri"  # Directory containing DICOM files
VERBOSE=false
MAX_RETRIES=30  # Maximum number of retries
RETRY_INTERVAL=10  # Seconds between retries

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -v|--verbose)
      VERBOSE=true
      shift
      ;;
    -d|--directory)
      DICOM_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [-v|--verbose] [-d|--directory <directory>]"
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

# Check if the DICOM directory exists
if [ ! -d "$DICOM_DIR" ]; then
    echo "Error: DICOM directory not found at $DICOM_DIR"
    exit 1
fi

# Find all DICOM files in the directory
DICOM_FILES=($(find "$DICOM_DIR" -type f -name "*.dcm"))
if [ ${#DICOM_FILES[@]} -eq 0 ]; then
    echo "Error: No DICOM files found in $DICOM_DIR"
    exit 1
fi

echo "Found ${#DICOM_FILES[@]} DICOM files in $DICOM_DIR"

# Upload first DICOM file to Orthanc to create the study
echo "Uploading first DICOM file to create study..."
FIRST_FILE="${DICOM_FILES[0]}"
UPLOAD_RESPONSE=$(curl $CURL_VERBOSE -s -X POST "${ROUTER_URL}/instances" --data-binary "@${FIRST_FILE}")
STUDY_ID=$(echo "$UPLOAD_RESPONSE" | jq -r '.ParentStudy')

if [ -z "$STUDY_ID" ] || [ "$STUDY_ID" = "null" ]; then
    echo "Error: Failed to get ParentStudy from upload response"
    echo "Response: $UPLOAD_RESPONSE"
    exit 1
fi

echo "Study ID: $STUDY_ID"

# Upload remaining DICOM files to the same study
for ((i=1; i<${#DICOM_FILES[@]}; i++)); do
    echo "Uploading DICOM file ${DICOM_FILES[$i]} to study..."
    curl $CURL_VERBOSE -s -X POST "${ROUTER_URL}/instances" --data-binary "@${DICOM_FILES[$i]}"
done

# Wait for the study to be processed by the AI model with retries
echo "Waiting for the study to be processed by the AI model (this may take a while)..."
RETRY_COUNT=0
STUDY_PROCESSED=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$STUDY_PROCESSED" = false ]; do
    echo "Attempt $((RETRY_COUNT + 1)) of $MAX_RETRIES..."
    
    # Check if the study has been processed in the viewer
    STUDY_DETAILS=$(curl $CURL_VERBOSE -s -X GET "${VIEWER_URL}/studies/${STUDY_ID}")
    INSTANCES=$(echo "$STUDY_DETAILS" | jq -r '.Instances')
    
    if [ ! -z "$INSTANCES" ] && [ "$INSTANCES" != "null" ] && [ "$INSTANCES" != "[]" ]; then
        NUM_INSTANCES=$(echo "$INSTANCES" | jq 'length')
        echo "Found $NUM_INSTANCES instances in the study"
        
        # Check if we have more instances than we uploaded (indicating AI processing)
        if [ $NUM_INSTANCES -gt ${#DICOM_FILES[@]} ]; then
            STUDY_PROCESSED=true
            echo "Study has been processed by AI"
        else
            echo "Study found but not yet processed by AI"
        fi
    else
        echo "No instances found in study yet"
    fi
    
    if [ "$STUDY_PROCESSED" = false ]; then
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            echo "Waiting $RETRY_INTERVAL seconds before next attempt..."
            sleep $RETRY_INTERVAL
        fi
    fi
done

if [ "$STUDY_PROCESSED" = false ]; then
    echo "Error: Study was not processed within the timeout period"
    exit 1
fi

# Get the original instances and the AI-processed instances from the viewer
ORIGINAL_INSTANCES=$(echo "$INSTANCES" | jq -r '.[:-2]')  # All except the last two (SR and SC)
AI_INSTANCES=$(echo "$INSTANCES" | jq -r '.[-2:]')  # The last two (SR and SC)

echo "Original instances: $ORIGINAL_INSTANCES"
echo "AI-processed instances: $AI_INSTANCES"

# Get details of the AI-processed instances from the viewer
for INSTANCE_ID in $(echo "$AI_INSTANCES" | jq -r '.[]'); do
    echo "Getting details for instance $INSTANCE_ID..."
    INSTANCE_DETAILS=$(curl $CURL_VERBOSE -s -X GET "${VIEWER_URL}/instances/${INSTANCE_ID}")
    MODALITY=$(echo "$INSTANCE_DETAILS" | jq -r '.MainDicomTags.Modality')
    echo "Instance $INSTANCE_ID has modality: $MODALITY"
    
    # If it's an SR, get the content
    if [ "$MODALITY" = "SR" ]; then
        echo "Getting SR content..."
        SR_CONTENT=$(curl $CURL_VERBOSE -s -X GET "${VIEWER_URL}/instances/${INSTANCE_ID}/content")
        echo "SR content: $SR_CONTENT"
    fi
done

echo "Test completed successfully!" 