FROM docker.io/osimis/orthanc

RUN pip3 install pydicom 
RUN pip3 install dicomweb-client 

RUN mkdir /python
COPY * /python/