from pathlib import Path
from tempfile import TemporaryDirectory

from pydicom.dataset import Dataset

from pynetdicom import AE, debug_logger, evt, StoragePresentationContexts
from pynetdicom.sop_class import (StudyRootQueryRetrieveInformationModelMove, 
                                    StudyRootQueryRetrieveInformationModelFind,
                                    PatientRootQueryRetrieveInformationModelFind)

# In case of Problems, enable the debug logger to see DICOM infos
#debug_logger()

class PynetdicomWrapper:
    """Class to simplify download of QA images from an Aria Database.

    The latest RTImages from a given Patient/RTPlan combination can be downloaded
    to a given directory (temporary folder). DICOM AE information are have default
    values for convenience.
    """

    def __init__(self, pat_id: str='', plan_name: str='') -> None:
        """
        Parameters:
            patid : str
                Patient ID string from database
            planname : str
                Planname 
        """
        # DICOM SCU/SCP config options
        self.local_aet = 'QATRACK'
        self.local_ip = '192.168.1.1'
        self.local_port = 9999

        self.remote_aet = 'ESAPI'
        self.remote_ip = '192.168.1.2'
        self.remote_port = 51402

        self.pat_id = pat_id
        self.plan_name = plan_name

        self.plan_uid = ''
        self.study_uid = ''

        if self.pat_id and self.plan_name:
            self.plan_uid, self.study_uid = self.get_plan_uids(self.pat_id, self.plan_name)
            
    
    def handle_store(self, event, path: Path) -> int:
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
                            
        # Save the dataset using the SOP Instance UID as the filename
        ds.save_as(outfile, write_like_original=False)
                            
        # Return a 'Success' status
        return 0x0000


    def get_plan_uids(self, pat_id: str, plan_name:str) -> dict:
        """Function to search for SOPInstanceUID and StudyInstanceUID 
        of a given plan using Patient ID.
        
        Parameters:
            patid : str
                Patient ID string from database
            planname : str
                RTPlan name 
        Raises:
            ValueError: If none or more than one matching plan is found.

        Returns:
            Dict with SOPInstanceUID and StudyInstanceUID.
        """

        # Initialise the Application Entity
        ae = AE(ae_title=self.local_aet)

        # Add requested presentation context for study query retrieve find
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)

        # Create identifier (query) dataset for Series Query
        find_plan_ds = Dataset()
        find_plan_ds.QueryRetrieveLevel = 'IMAGE'
        find_plan_ds.Modality = 'RTPLAN'
        find_plan_ds.PatientID = pat_id
        find_plan_ds.RTPlanLabel = plan_name
        # Information we are interested in:
        find_plan_ds.SOPInstanceUID = ''
        find_plan_ds.StudyInstanceUID = ''

        # Associate with the peer AE at IP 10.128.140.11 and port 51402
        assoc = ae.associate(self.remote_ip, self.remote_port, ae_title=self.remote_aet)
        
        identifier_list = []

        if assoc.is_established:
            # find all matching RTPlans in the given patient.
            find_responses = assoc.send_c_find(find_plan_ds, StudyRootQueryRetrieveInformationModelFind)
            for (status, identifier) in find_responses:
                if status and identifier is not None:
                    identifier_list.append(identifier)
                #else:
                #    print(f"Finished retrieving series in study, final status is {status.Status:#06x}.")   

        assoc.release()

        # there should be only one result, so we are doing some checks:
        if len(identifier_list) == 1:   
            return identifier_list[0].SOPInstanceUID, identifier_list[0].StudyInstanceUID

        elif len(identifier_list) < 1:
            raise ValueError(f"No plan SOPInstanceUID found for plan name {plan_name}")

        else:
            raise ValueError(f"More than one plan found with name {plan_name}")

        return None
    

    def get_latest_series(self, path: Path, imagetype: str, ignore_kV: bool=True, 
                            plan_uid: str='', study_uid: str='', ) -> str:
        """Function to wrap the pynetdicom commands to make it easier to
        use the method in qatrack+. Querys the fixed DICOM SCP for the latest
        Series in the given Study.

        Parameters:
            path : Path
                Path to the temporary outputfolder for the DICOM Move operation
            imagetype : string
                DICOM ImageType (0008, 0008) you are looking for. A.e.
                Portal ('ORIGINAL\PRIMARY\PORTAL') or
                Portal Dose ('ORIGINAL\PRIMARY\PORTAL\ACQUIRED_DOSE')     
            ignore_kV: bool
                Do not move kV images, only MV. 
            plan_uid: string
                SOPInstanceUID
            study_uid : string
                StudyInstanceUID (0020, 000d) of the Study you want to grep the
                lastes Series from.

        Raises:
            RuntimeError: When no matching images (DICOM objects) are found
            ConnectionError: When the connection can't be established or gets lost

        Returns:
            Date+Time string of the DICOM object acquisition

        """ 
        if not plan_uid and self.plan_uid:
            plan_uid = self.plan_uid
        else:
            raise TypeError("Missing 1 required argument: plan_uid.")

        if not study_uid and self.plan_uid:
            study_uid = self.study_uid
        else:
            raise TypeError("Missing 1 required argument: study_uid.")
     
        # Initialise the Application Entity
        ae = AE(ae_title=self.local_aet)

        # Add requested presentation context for study query retrieve find and move
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove)

        # Add the Storage SCP's supported presentationContexts
        ae.supported_contexts = StoragePresentationContexts

        # Start our Storage SCP in non-blocking mode, listening on Port 9999 (open port in firewall!)
        handlers = [(evt.EVT_C_STORE, self.handle_store, [path])]
        scp = ae.start_server((self.local_ip, self.local_port), block= False, evt_handlers=handlers)

        # Create identifier (query) dataset for Series Query
        find_series_ds = Dataset()
        find_series_ds.QueryRetrieveLevel = 'SERIES'
        find_series_ds.Modality = 'RTIMAGE'
        find_series_ds.StudyInstanceUID = study_uid
        # Information we are interested in:
        find_series_ds.SeriesInstanceUID = ''

        # Image Level Find Dataset for Image Query
        find_image_ds = Dataset()
        find_image_ds.QueryRetrieveLevel = 'IMAGE'
        find_image_ds.Modality = 'RTIMAGE'
        find_image_ds.StudyInstanceUID = study_uid
        find_image_ds.ImageType = imagetype
        # Information we are interested in:
        find_image_ds.SeriesInstanceUID = ''
        find_image_ds.AcquisitionDate = ''
        find_image_ds.AcquisitionTime = ''
        find_image_ds.ReferencedRTPlanSequence = []

        # Create/copy identifier (move) dataset
        move_ds = find_series_ds
        if ignore_kV:
            move_ds.PrimaryDosimeterUnit = 'MU' # ignore kV images which have "MINUTE" here

        # list for all SeriesInstanceUIDs from given study
        identifier_list = []
        # list for tuples with date+time and SeriesInstanceUIDs
        date_suid_list = []
        # variable for latest date+time to return
        latest_datetime = ''

        # Associate with the peer AE at IP 10.128.140.11 and port 51402
        assoc = ae.associate(self.remote_ip, self.remote_port, ae_title=self.remote_aet)

        if assoc.is_established:
            # first find all series in the given study
            find_responses = assoc.send_c_find(find_series_ds, StudyRootQueryRetrieveInformationModelFind)
            for (status, identifier) in find_responses:
                if status and identifier is not None:
                    identifier_list.append(identifier)
                #else:
                #    print(f"Finished retrieving series in study, final status is {status.Status:#06x}.")   

            # get date+time from images of all series to search for the latest series
            for ds in identifier_list:
                tmp_list = []
                find_image_ds.SeriesInstanceUID = ds.SeriesInstanceUID
                find_image_responses = assoc.send_c_find(find_image_ds, StudyRootQueryRetrieveInformationModelFind)
                for (status, identifier) in find_image_responses:            
                    if status and identifier is not None:
                        tmp_list.append(identifier)

                # keep only date+time and SeriesInstanceUID from images that reference the correct plan
                if tmp_list and tmp_list[0].ReferencedRTPlanSequence:
                    if tmp_list[0].ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID == plan_uid:
                        date_suid_list.append((tmp_list[0].AcquisitionDate + tmp_list[0].AcquisitionTime,
                                               tmp_list[0].SeriesInstanceUID))             
            
            # If we found any images select the latest SeriesInstanceUID and move the series
            if date_suid_list:
                latest_datetime, move_ds.SeriesInstanceUID = sorted(date_suid_list, reverse=True)[0]

                # Use the C-MOVE service to send the identifier and store images with our scp
                move_responses = assoc.send_c_move(move_ds, self.local_aet, StudyRootQueryRetrieveInformationModelMove)
                for (status, identifier) in move_responses:
                    if not status.Status in [0x0000, 0xFF00]:            
                        assoc.release()
                        scp.shutdown()
                        raise ConnectionError(f'Connection timed out, was aborted or received invalid response. Status code: {status.Status:#06x}')
            
            else:
                assoc.release()
                scp.shutdown()
                raise RuntimeError('No DICOM objects found or received.')

            # Release the association
            assoc.release()

        else: # no association could be established
            scp.shutdown()
            raise ConnectionError('Association rejected, aborted or never connected.')

        # Transfers done, stopping the scp.
        scp.shutdown()

        return latest_datetime
