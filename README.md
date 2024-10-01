# pynetdicom_wrapper
A wrapper for pynetdicom to fetch DICOM images from Aria and store them in a directory for usage in QATrack+.

## Setup Instructions
There are three steps to take to be able to use the pynetdicom_wrapper script/module: Configure the Aria DB Daemon, install pynetdicom and pynetdicom_wrapper inside your Qatrack+ virtual environment and finally set up the QATrack+ test lists.

### Aria DICOM Service
In order to fetch DICOM images from Aria you first have to configure the DICOM Service in Aria to provide a "DB Service". There are in depth instructions in the [VarianApiBook Chapter 4](https://varianapis.github.io/VarianApiBook.pdf) which cover that topic. In most cases the software will probably be installed and you only have to add a "DB Service". AE title and port number can be chosen freely, the IPs are the ones from the Aria Server the DICOM service is running on and the QATrack+ server.

![Screenshot DB Service](./files/DBService01.png)

### Pynetdicom
To use the pynetdicom_wrapper you first have to "pip install pynetdicom" (don't forget to activate your QATrack+ virtual environment). After that you can download the pynetdicom_wrapper folder and its contents and copy it to the site-packages (for example ~/venvs/qatrack31/lib/python3.10/site-packages/). Since the wrapper should allow for as few lines of code as possible in QATrack+ the connection to the Aria DB is hardcoded inside pynetdicom_wrapper.py __init__() method (lines 31 onward).
```Python
 52     # DICOM SCU/SCP config options
 53     self.local_aet = 'QATRACK'
 54     self.local_ip = '192.168.1.1'
 55     self.local_port = 9999
 56
 57     self.remote_aet = 'ESAPI'
 58     self.remote_ip = '192.168.1.2'
 59     self.remote_port = 51402
```
(If you want to set the variables on the fly you can do that when you ommit passing pat_id and plan_name when creating your PynetdicomWrapper instance and call get_plan_uids by hand.)

### QATrack+
First you have to make sure, your server firewall is accepting connections from the Aria DB Service on your 'local_port'. Then, in QATrack+, you have to set up two string tests for the patient ID and the RTPlan name, one string-composite test for the code and some more composite/string-composite tests for the results. If you want to also have the option to start the download after you had time to set patient ID and plan name you can add an additional boolean test (see [testpack](./files/WL6X.tpk) in the files folder).

## Usage
When using the pynetdicom_wrapper you first create an instance of PynetdicomWrapper with the patient ID and the plan name as parameters. After that you call the .get_latest_series() method with at least giving a Path to a (temporary) directory were the images can be stored in and the image type. The temporary directory can be created with the "tempfile" module from the python standard library (see example). The imagetype is in DICOM Tag (0008,0008) it should be either "ORIGINAL\PRIMARY\PORTAL" for normal portal images or "ORIGINAL\PRIMARY\PORTAL\ACQUIRED_DOSE" for portal dose images.

get_latest_series() writes the files to the given directory (if anything is found) and returns the date+time string taken from the DICOM objects in case you want to write that to a test also.
If you also want to download the kV images from the series you can set ignore_kV to False.

## Example
A simple test script utilizing the wrapper to grep the lastest Winston Lutz images and analyze them with pylinac would be something like this:
```Python
from pathlib import Path
from tempfile import TemporaryDirectory
from pylinac import WinstonLutz
from pynetdicom_wrapper import PynetdicomWrapper

temp_dir = TemporaryDirectory()
outputpath = Path(tempDir.name)

pndw = PynetdicomWrapper('QA_TB_WL', 'WL_10MV')
latest_date_time = pndw.get_latest_series(outputpath, 'ORIGINAL\PRIMARY\PORTAL')

wl = WinstonLutz(outputpath)
wl.analyze(bb_size_mm=5)
wl.publish_pdf('mywl.pdf')
```
