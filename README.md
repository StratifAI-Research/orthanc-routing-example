# Orthanc DICOM Routing with AI Integration

A demo project showcasing DICOM study routing between Orthanc servers, with automatic forwarding to an AI inference server when studies stabilize.

## Quick Test Guide

### 1. Upload Studies to Routing Server

Use the Orthanc Explorer web interface at http://localhost:8000/app/explorer.html#upload to upload DICOM studies.

![Orthanc Explorer Upload](screenshots/orthanc-web-upload.png)  
*Web interface for uploading DICOM files*

---

### 2. Verify Study in Routing Server

1. Access Orthanc Explorer: http://localhost:8000/ui/app/index.html
![Routing Server Studies](screenshots/routing-server-studies.png)  
*Studies list in Orthanc Viewer*

---

### 3. Check AI Server Reception

1. Access AI Orthanc: http://localhost:8001/ui/app/index.html#/
![AI Server Studies](screenshots/ai-server-studies.png)  
*Received studies in AI Orthanc*

2. Check processing status in the AI server interface.
