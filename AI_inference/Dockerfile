FROM docker.io/orthancteam/orthanc

RUN pip3 install pydicom --break-system-packages
RUN pip3 install dicomweb-client --break-system-packages

RUN mkdir /python
COPY * /python/