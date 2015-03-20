### Installation

```
virtualenv reaperenv
source reaperenv/bin/activate
pip install -U pip setuptools

git clone https://github.com/scitran/reaper.git
pip install -e reaper
```

### Reaping

```
pfile_reaper <path>
dicom_reaper <host> <port> <return port> reaper <scanner AET>
```


### Debugging

```
findscu --verbose -S -aet reaper -aec <scanner AET> -k QueryRetrieveLevel="STUDY" -k StudyDate="" <host> <port>
findscu --verbose -S -aet reaper -aec <scanner AET> -k QueryRetrieveLevel="SERIES" -k StudyDate="" <host> <port>
```
