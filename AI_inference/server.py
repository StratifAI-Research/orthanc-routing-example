import orthanc
import requests
import uuid

def StartAI(output, uri, study_id):
    """
    Function to start AI job, given StudyID
    returns: 
    job_uuid: int - job_uuid of new job started
    """
    print('Starting AI job for: %s' % study_id)
    ### Start AI processing
    ##
    job_uuid = uuid.uuid4()
    output.AnswerBuffer(job_uuid, 'text/plain')

def AIJobStatus(output, uri, job_uuid):
    print('Accessing uri: %s' % uri)
    if check_job(job_uuid):
        output.AnswerBuffer('ok\n', 'text/plain')
    else:
        output.AnswerBuffer('done\n', 'text/plain')

def SendAIResult(changeType, level, resourceId):
    if changeType == orthanc.ChangeType.STABLE_STUDY:
        print('Stable study: %s' % resourceId)
        request = {"Resources" : [resourceId]}
        print(request)
        requests.post(url="http://127.0.0.1:8042/dicom-web/servers/ai/stow/",json=request)

orthanc.RegisterOnChangeCallback(SendAIResult)
orthanc.RegisterRestCallback('/start_ai', StartAI)
orthanc.RegisterRestCallback('/ai_status', AIJobStatus)