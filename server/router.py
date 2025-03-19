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
            if tags.get("SeriesDescription") == "AI_Processed":
                return True
        return False
    except Exception as e:
        print(f"Error checking AI marker: {str(e)}")
        return False


def OnChange(changeType, level, resourceId):
    if changeType == orthanc.ChangeType.STABLE_STUDY:
        print(f"Stable study: {resourceId}")

        if IsAiProcessed(resourceId):
            print(f"Study {resourceId} already contains AI results - skipping")
            return

        try:
            request = {"Resources": [resourceId]}
            response = requests.post(
                "http://localhost:8042/dicom-web/servers/ai/stow/",
                json=request,
                timeout=10,
            )
            response.raise_for_status()
            print(f"Successfully forwarded study {resourceId}")
        except Exception as e:
            print(f"Failed to forward study {resourceId}: {str(e)}")


orthanc.RegisterOnChangeCallback(OnChange)
