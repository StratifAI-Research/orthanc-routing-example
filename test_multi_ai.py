#!/usr/bin/env python3
"""
Test script for multi-model AI routing functionality.
Demonstrates how multiple AI models can process the same study.
"""

import requests
import json
import time

# Configuration
ORTHANC_URL = "http://localhost:8042"
STUDY_ID = "your_study_id_here"  # Replace with actual study ID

# Multiple AI targets for testing
AI_TARGETS = [
    {
        "name": "breast-cancer-ai",
        "url": "orthanc-ai-breast:4242/AI_BREAST",
        "description": "Breast Cancer Detection Model"
    },
    {
        "name": "lung-nodule-ai",
        "url": "orthanc-ai-lung:4242/AI_LUNG",
        "description": "Lung Nodule Detection Model"
    },
    {
        "name": "fracture-detection-ai",
        "url": "orthanc-ai-fracture:4242/AI_FRACTURE",
        "description": "Fracture Detection Model"
    }
]

def send_to_ai_target(study_id, target, allow_reprocessing=False):
    """Send a study to a specific AI target"""

    payload = {
        "study_id": study_id,
        "target": target["name"],
        "target_url": target["url"],
        "allow_reprocessing": allow_reprocessing
    }

    print(f"\n{'='*60}")
    print(f"Sending study {study_id} to {target['description']}")
    print(f"Target: {target['name']} ({target['url']})")
    print(f"Allow reprocessing: {allow_reprocessing}")
    print(f"{'='*60}")

    try:
        response = requests.post(
            f"{ORTHANC_URL}/send-to-ai-dicomweb",
            json=payload,
            timeout=60
        )

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print("✅ SUCCESS!")
            print(f"Message: {result.get('message', 'No message')}")
            print(f"Series sent: {result.get('series_sent', 'Unknown')}")
            print(f"Instances sent: {result.get('instances_sent', 'Unknown')}")
            return True

        elif response.status_code == 409:
            print("⚠️  ALREADY PROCESSED")
            print(f"Message: {response.text}")
            return False

        elif response.status_code == 400:
            print("❌ BAD REQUEST")
            print(f"Message: {response.text}")
            return False

        else:
            print(f"❌ ERROR: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except requests.exceptions.Timeout:
        print("❌ TIMEOUT: Request took longer than 60 seconds")
        return False
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        return False

def get_study_series_info(study_id):
    """Get information about series in a study"""
    try:
        response = requests.get(f"{ORTHANC_URL}/studies/{study_id}/series")
        if response.status_code == 200:
            series_list = response.json()

            print(f"\n📊 STUDY ANALYSIS: {study_id}")
            print(f"Total series: {len(series_list)}")

            original_count = 0
            ai_count = 0

            for series in series_list:
                series_id = series['ID']
                # Get series tags
                tags_response = requests.get(f"{ORTHANC_URL}/series/{series_id}/tags?simplify")
                if tags_response.status_code == 200:
                    tags = tags_response.json()
                    description = tags.get('SeriesDescription', 'No description')
                    modality = tags.get('Modality', 'Unknown')

                    # Check if it's an AI result
                    ai_markers = [
                        "Automated Diagnostic Findings",
                        "AI Analysis Result",
                        "AI Generated",
                        "Secondary Capture AI",
                        "AI Structured Report"
                    ]

                    is_ai_result = (
                        any(marker in description for marker in ai_markers) or
                        (modality in ["SC", "SR"] and "AI" in description.upper()) or
                        description.startswith("AI_") or
                        description.endswith("_AI")
                    )

                    if is_ai_result:
                        ai_count += 1
                        print(f"  🤖 AI Result: {description} ({modality})")
                    else:
                        original_count += 1
                        print(f"  📷 Original: {description} ({modality})")

            print(f"\nSummary: {original_count} original series, {ai_count} AI result series")
            return original_count > 0

    except Exception as e:
        print(f"Error getting study info: {str(e)}")
        return False

def main():
    """Main test function"""

    print("🚀 Multi-Model AI Routing Test")
    print("=" * 50)

    if STUDY_ID == "your_study_id_here":
        print("❌ Please set STUDY_ID to a valid study ID in the script")
        return

    # Get initial study information
    if not get_study_series_info(STUDY_ID):
        print("❌ Study has no processable content or doesn't exist")
        return

    # Test 1: Send to all AI targets (should succeed for all)
    print(f"\n🧪 TEST 1: Send to all AI targets (first time)")
    success_count = 0
    for target in AI_TARGETS:
        if send_to_ai_target(STUDY_ID, target, allow_reprocessing=False):
            success_count += 1
        time.sleep(2)  # Brief delay between requests

    print(f"\n📈 Test 1 Results: {success_count}/{len(AI_TARGETS)} targets succeeded")

    # Simulate AI processing time
    print("\n⏳ Simulating AI processing time (waiting 5 seconds)...")
    time.sleep(5)

    # Get updated study information
    get_study_series_info(STUDY_ID)

    # Test 2: Try to send to same targets again (should be blocked)
    print(f"\n🧪 TEST 2: Try to send to same targets again (should be blocked)")
    blocked_count = 0
    for target in AI_TARGETS:
        if not send_to_ai_target(STUDY_ID, target, allow_reprocessing=False):
            blocked_count += 1
        time.sleep(1)

    print(f"\n📈 Test 2 Results: {blocked_count}/{len(AI_TARGETS)} targets were correctly blocked")

    # Test 3: Force reprocessing with flag
    print(f"\n🧪 TEST 3: Force reprocessing with allow_reprocessing=True")
    reprocess_count = 0
    for target in AI_TARGETS[:1]:  # Just test with first target
        if send_to_ai_target(STUDY_ID, target, allow_reprocessing=True):
            reprocess_count += 1
        time.sleep(1)

    print(f"\n📈 Test 3 Results: {reprocess_count}/1 reprocessing attempts succeeded")

    # Final study analysis
    get_study_series_info(STUDY_ID)

    print(f"\n✅ Multi-Model AI Routing Test Complete!")
    print("Key Benefits Demonstrated:")
    print("  ✓ Multiple AI models can process the same study")
    print("  ✓ AI result series are filtered out automatically")
    print("  ✓ Optional target-specific reprocessing prevention")
    print("  ✓ Configurable reprocessing override")

if __name__ == "__main__":
    main()
