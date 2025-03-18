import orthanc
import requests


def OnChange(changeType, level, resourceId):
    if changeType == orthanc.ChangeType.STABLE_STUDY:
        print("Stable study: %s" % resourceId)
        request = {"Resources": [resourceId]}
        print(request)
        requests.post(
            url="http://localhost:8042/dicom-web/servers/ai/stow/", json=request
        )

        # orthanc.RestApiPost('/modalities/ai/store', resourceId)


orthanc.RegisterOnChangeCallback(OnChange)
