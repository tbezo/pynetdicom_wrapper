"""Module providing the basic datasets"""
from pydicom import Dataset


def return_find_plan_ds(pat_id: str, plan_name: str) -> Dataset:
    """Dataset for image level query"""
    ds = Dataset()
    ds.QueryRetrieveLevel = 'IMAGE'
    ds.Modality = 'RTPLAN'
    ds.PatientID = pat_id
    ds.RTPlanLabel = plan_name
    # Information we are interested in:
    ds.SOPInstanceUID = ''
    ds.StudyInstanceUID = ''

    return ds


def return_find_image_ds(study_uid: str, imagetype: str) -> Dataset:
    """Return Dataset for image level query"""
    ds = Dataset()
    ds.QueryRetrieveLevel = 'IMAGE'
    ds.Modality = 'RTIMAGE'
    ds.StudyInstanceUID = study_uid
    ds.ImageType = imagetype
    # Information we are interested in:
    ds.SeriesInstanceUID = ''
    ds.AcquisitionDate = ''
    ds.AcquisitionTime = ''
    ds.ReferencedRTPlanSequence = []

    return ds


def return_find_series_ds(study_uid: str) -> Dataset:
    """Return Dataset for series level query"""
    ds = Dataset()
    ds.QueryRetrieveLevel = 'SERIES'
    ds.Modality = 'RTIMAGE'
    ds.StudyInstanceUID = study_uid
    # Information we are interested in:
    ds.SeriesInstanceUID = ''

    return ds


class AEConfig:
    """Holds AE title, IP and port"""
    def __init__(self, aet: str, ip: str, port: int):
        """
        Parameters:
        -----------
        aet: str
        DICOM Application Entity Title
        ip: str
        IP associated with the AE
        port: int
        Port the AE is listening on
        """
        self.aet = aet
        self.ip = ip
        self.port = port

    def __rep__(self) -> str:
        return f"AEConfig, AET: {self.aet}, IP: {self.ip}, Port: {self.port}"

    def __str__(self) -> str:
        return f"{self.aet} - {self.ip}:{self.port}"

    @property
    def ip(self):
        """IP of the AE"""
        return self._ip

    @ip.setter
    def ip(self, value: str):
        """Set value of ip after checks"""
        subs = value.split('.')
        if len(subs) == 4:
            self._ip = value
        else:
            raise ValueError("IP wrong formatted")

    @property
    def aet(self):
        """AE Title"""
        return self._aet

    @aet.setter
    def aet(self, value: str):
        """AE Title setter to keep length below 17 (also checked by pynetdicom)"""
        value = value.strip()
        if len(value) < 17:
            self._aet = value
        else:
            self._aet = value[0:16]

    @property
    def port(self):
        """Port Number for AE"""
        return self._port

    @port.setter
    def port(self, value):
        """Port setter to keep below limit"""
        if value in range(65536):
            self._port = value
        else:
            raise ValueError("Port number out of range")
