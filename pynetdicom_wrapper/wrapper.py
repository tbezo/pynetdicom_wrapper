"""Module providing the main PynetdicomWrapper class"""
from pathlib import Path
from datetime import date

from pynetdicom import AE, debug_logger, evt, StoragePresentationContexts
from pynetdicom.sop_class import (StudyRootQueryRetrieveInformationModelMove,
                                  StudyRootQueryRetrieveInformationModelFind,
                                  PatientRootQueryRetrieveInformationModelFind)

import pynetdicom_wrapper.datasets as dset

# In case of Problems, enable the debug logger to see DICOM infos
# debug_logger()


class PynetdicomWrapper:
    """Class to simplify download of QA images from an Aria Database.

    The latest RTImages from a given Patient/RTPlan combination can be
    downloaded to a given directory (temporary folder). DICOM AE information
    are have default values for convenience.
    """

    def __init__(self, pat_id: str = '', plan_name: str = '') -> None:
        """
        Parameters:
            patid : str
                Patient ID string from database
            planname : str
                Planname
        """
        # DICOM SCU/SCP config options
        self.local_conf = dset.AEConfig(aet='QATRACK', ip='192.186.1.1', port=9999)
        self.remote_conf = dset.AEConfig(aet='ESAPI', ip='192.168.1.2', port=51402)

        self.pat_id = pat_id
        self.plan_name = plan_name

        self.plan_uid = ''
        self.study_uid = ''

        if self.pat_id and self.plan_name:
            self.get_plan_uids(self.pat_id, self.plan_name)

    @staticmethod
    def handle_store(event, path: Path, ignore_kV: bool = True) -> int:
        """Handle a C-STORE request event (write to path).
        Handler for pynetdicom evt.EVT_C_STORE. Always returns success!

        Parameters:
            path: Path
                Path were DICOM Objects are stored in.

        Returns:
            0x0000 (success)
        """
        ds = event.dataset
        ds.file_meta = event.file_meta

        outfile = path / (ds.SOPInstanceUID + '.dcm')

        # ignore kV images which have PrimaryDosimeterUnit "MINUTE"
        if ignore_kV and ds.PrimaryDosimeterUnit == 'MINUTE':
            return 0x0000

        # else save the dataset using the SOP Instance UID as the filename
        ds.save_as(outfile, write_like_original=False)
        # Return a 'Success' status
        return 0x0000

    def get_plan_uids(self, pat_id: str, plan_name: str):
        """Function to search for plan_uid (SOPInstanceUID) and
        study_uid (StudyInstanceUID) of a given plan using Patient ID.
        (Method is run by __init__() if Patient ID and Plan Id are provided).

        Parameters:
            patid : str
                Patient ID string from database
            planname : str
                RTPlan name
        Raises:
            ValueError: If none or more than one matching plan is found.
        """

        # Initialise the Application Entity
        ae = AE(ae_title=self.local_conf.aet)

        # Add requested presentation context for study query retrieve find
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)

        # Create identifier (query) dataset for Series Query
        find_plan_ds = dset.return_find_plan_ds(pat_id, plan_name)

        # Associate with the peer AE at IP 10.128.140.11 and port 51402
        assoc = ae.associate(self.remote_conf.ip,
                             self.remote_conf.port,
                             ae_title=self.remote_conf.aet)

        identifier_list = []

        if assoc.is_established:
            # find all matching RTPlans in the given patient.
            find_responses = assoc.send_c_find(find_plan_ds,
                                               StudyRootQueryRetrieveInformationModelFind)
            identifier_list = [identifier for status, identifier in find_responses
                               if status and identifier is not None]

            assoc.release()
        else:  # no association could be established
            raise ConnectionError(f'Association with {self.remote_conf} rejected, '
                                  f'aborted or never connected.')

        # Only one result allowed, so we are doing some checks:
        if len(identifier_list) == 1:
            self.plan_uid = identifier_list[0].SOPInstanceUID
            self.study_uid = identifier_list[0].StudyInstanceUID
        elif len(identifier_list) < 1:
            raise ValueError(f"No plan SOPInstanceUID found for plan name {plan_name}")
        else:
            raise ValueError(f"More than one plan found with name {plan_name}")


    def get_series(self, path: Path, imagetype: str, seriesdate: date | None = None,
                           ignore_kV: bool = True) -> str:
        r"""Function to wrap the pynetdicom commands to make it easier to
        use the method in qatrack+. Querys the fixed DICOM SCP for the latest
        Series (from date seriesdate) in the given Study.

        Parameters:
            path : Path
                Path to the temporary outputfolder for the DICOM Move operation
            imagetype : string
                DICOM ImageType (0008, 0008) you are looking for. A.e.
                Portal ('ORIGINAL\PRIMARY\PORTAL') or
                Portal Dose ('ORIGINAL\PRIMARY\PORTAL\ACQUIRED_DOSE')
            seriesdate: date
                Optional date object with date the series was acquired on.
            ignore_kV: bool
                Do not move kV images, only MV.

        Raises:
            RuntimeError: When no matching images (DICOM objects) are found.
            ConnectionError: When the connection can't be established or gets lost.
            TypeError: When plan_uid or study_uid are not present.

        Returns:
            Date+Time string of the DICOM object acquisition

        """
        if not self.plan_uid and self.study_uid:
            raise TypeError("Missing uid, call PynetdicomWrapper.get_plan_uids() first.")

        # Create identifier (query) dataset for Series Query with study_uid from plan.
        find_series_ds = dset.return_find_series_ds(self.study_uid)

        # Image Level Find Dataset for Image Query
        find_image_ds = dset.return_find_image_ds(self.study_uid, imagetype)
        if seriesdate is not None:
            find_image_ds.AcquisitionDate = seriesdate.strftime("%Y%m%d")

        # Create/copy identifier (move) dataset
        move_ds = find_series_ds
#        if ignore_kV:
#            move_ds.PrimaryDosimeterUnit = 'MU'  # ignore kV images which have "MINUTE" here

        # List for tuples with date+time and SeriesInstanceUIDs
        date_suid_list = []
        # Variable for date+time to return
        datetime = ''

        # Initialise the Application Entity
        ae = AE(ae_title=self.local_conf.aet)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove)
        ae.supported_contexts = StoragePresentationContexts

        # Start our Storage SCP in non-blocking mode, listening on Port 9999 (open port in FW!)
        handlers = [(evt.EVT_C_STORE, self.handle_store, [path, ignore_kV])]
        scp = ae.start_server((self.local_conf.ip, self.local_conf.port),
                              block=False, evt_handlers=handlers)

        # Associate with the peer AE at IP 192.168.1.1 and port 51402
        assoc = ae.associate(self.remote_conf.ip,
                             self.remote_conf.port,
                             ae_title=self.remote_conf.aet)

        if assoc.is_established:
            # First find all series (SeriesInstanceUIDs) in the given study (by plan_uid)
            find_series_responses = assoc.send_c_find(find_series_ds,
                                                      StudyRootQueryRetrieveInformationModelFind)
            series_identifier_list = [identifier for status, identifier in find_series_responses
                                      if status and identifier is not None]

            # Get date+time info from images of all series (from that seriesdate).
            for ds in series_identifier_list:
                find_image_ds.SeriesInstanceUID = ds.SeriesInstanceUID
                find_image_responses = assoc.send_c_find(find_image_ds,
                                                         StudyRootQueryRetrieveInformationModelFind)
                tmp_list = [identifier for status, identifier in find_image_responses
                            if status and identifier is not None]

                # keep only date+time and SeriesInstanceUID from images that reference the plan
                if tmp_list and tmp_list[0].ReferencedRTPlanSequence:
                    plan_uid = tmp_list[0].ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID
                    if plan_uid == self.plan_uid:
                        date_suid_list.append((tmp_list[0].AcquisitionDate +
                                               tmp_list[0].AcquisitionTime,
                                               tmp_list[0].SeriesInstanceUID))

            # If we found any images select the latest SeriesInstanceUID and move the series
            if date_suid_list:
                datetime, move_ds.SeriesInstanceUID = sorted(date_suid_list, reverse=True)[0]

                # Use the C-MOVE service to send the identifier and store images with our scp
                move_responses = assoc.send_c_move(move_ds, self.local_conf.aet,
                                                   StudyRootQueryRetrieveInformationModelMove)
                for (status, identifier) in move_responses:
                    if status.Status not in [0x0000, 0xFF00]:
                        assoc.release()
                        scp.shutdown()
                        raise ConnectionError(f'Connection timed out, was aborted or received'
                                              f'invalid response. Status code: '
                                              f'{status.Status:#06x}')

            else:
                assoc.release()
                scp.shutdown()
                raise RuntimeError('No DICOM objects found or received.')

            # Release the association
            assoc.release()

        else:  # no association could be established
            scp.shutdown()
            raise ConnectionError(f'Association with {self.remote_conf} rejected, '
                                  f'aborted or never connected.')

        # Transfers done, stopping the scp.
        scp.shutdown()

        return datetime
