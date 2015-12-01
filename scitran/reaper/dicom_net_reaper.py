#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

"""
apt-get -V install ipython python-virtualenv python-dev dcmtk
adduser --disabled-password --gecos "Scitran Reaper" reaper
"""

import logging
log = logging.getLogger('reaper.dicom')
#logging.getLogger('reaper.dicom.scu').setLevel(logging.INFO)

import os
import re
import dicom
import shutil
import hashlib
import datetime

import scu
import reaper
import gephysio

import scitran.data.medimg.dcm as scidcm
logging.getLogger('scitran.data').setLevel(logging.INFO)


class DicomNetReaper(reaper.Reaper):

    query_params = {
        'StudyInstanceUID': '',
        'SeriesInstanceUID': '',
        'StudyID': '',
        'SeriesNumber': '',
        'SeriesDate': '',
        'SeriesTime': '',
        'NumberOfSeriesRelatedInstances': '',
        'PatientID': '',
    }

    def __init__(self, options):
        if not all((options.get('host'), options.get('port'), options.get('return_port'), options.get('aet'), options.get('aec'))):
            log.error()
            sys.exit(1)
        self.scu = scu.SCU(options.get('host'), options.get('port'), options.get('return_port'), options.get('aet'), options.get('aec'))
        super(DicomNetReaper, self).__init__(self.scu.aec, options)
        self.anonymize = options.get('anonymize')
        self.whitelist = options.get('whitelist').replace('*','.*')
        self.blacklist = options.get('blacklist').split()
        self.peripheral_data_reapers['gephysio'] = gephysio.reap

    def state_str(self, _id, state):
        return '%s (%s)' % (_id, ', '.join(['%s %s' % (v, k) for k, v in state.iteritems()]))

    def instrument_query(self):
        i_state = {}
        scu_resp = self.scu.find(scu.SeriesQuery(**self.query_params))
        for r in scu_resp:
            state = {
                    'images': int(r['NumberOfSeriesRelatedInstances']),
                    'patient_id': r['PatientID'],
                    }
            i_state[r['SeriesInstanceUID']] = reaper.ReaperItem(state)
        return i_state or None # FIXME should return None only on communication error

    def reap(self, _id, item, tempdir):
        if item['state']['images'] == 0:
            log.info('ignoring     %s (zero images)' % _id)
            return None
        if item['state']['patient_id'] and not self.is_desired_patient_id(item['state']['patient_id']):
            return None
        reap_start = datetime.datetime.utcnow()
        log.info('reaping      %s' % self.state_str(_id, item['state']))
        success, reap_cnt = self.scu.move(scu.SeriesQuery(StudyInstanceUID='', SeriesInstanceUID=_id), tempdir)
        filepaths = [os.path.join(tempdir, filename) for filename in os.listdir(tempdir)]
        log.info('reaped       %s (%d images) in %.1fs' % (_id, reap_cnt, (datetime.datetime.utcnow() - reap_start).total_seconds()))
        if success and reap_cnt > 0:
            dcm = self.DicomFile(filepaths[0])
            if not self.is_desired_patient_id(dcm.patient_id):
                return None
        if success and reap_cnt == item['state']['images']:
            acq_info = self.split_into_acquisitions(_id, item, tempdir, filepaths)
            if self.peripheral_data:
                for ai in acq_info:
                    dcm = scidcm.Dicom(ai['path'], timezone=self.timezone)
                    self.reap_peripheral_data(tempdir, dcm, ai['prefix'], ai['log_info'])
            return True
        else:
            return False

    def is_desired_patient_id(self, patient_id):
        if not re.match(self.whitelist, patient_id):
            log.info('ignoring     %s (non-matching patient ID)' % _id)
            return False
        if patient_id.strip('/').lower() in self.blacklist:
            log.info('discarding   %s' % _id)
            return False
        return True

    def split_into_acquisitions(self, _id, item, path, filepaths):
        if self.anonymize:
            log.info('anonymizing  %s' % _id)
        dcm_dict = {}
        for filepath in filepaths:
            dcm = self.DicomFile(filepath, self.anonymize)
            if os.path.basename(filepath).startswith('(none)'):
                new_filepath = filepath.replace('(none)', 'NA')
                os.rename(filepath, new_filepath)
                filepath = new_filepath
            os.utime(filepath, (int(dcm.timestamp.strftime('%s')), int(dcm.timestamp.strftime('%s'))))  # correct timestamps
            dcm_dict.setdefault(dcm.acq_no, []).append(filepath)
        log.info('compressing  %s' % _id)
        acq_info = []
        for acq_no, acq_paths in dcm_dict.iteritems():
            name_prefix = _id + ('_' + acq_no if acq_no is not None else '')
            dir_name = name_prefix + '_' + scidcm.Dicom.filetype
            arcdir_path = os.path.join(path, dir_name)
            os.mkdir(arcdir_path)
            for filepath in acq_paths:
                os.rename(filepath, '%s.dcm' % os.path.join(arcdir_path, os.path.basename(filepath)))
            metadata = {
                    'filetype': scidcm.Dicom.filetype,
                    'timezone': self.timezone,
                    'overwrite': {
                        'firstname_hash': dcm.firstname_hash,
                        'lastname_hash': dcm.lastname_hash,
                        }
                    }
            reaper.create_archive(arcdir_path+'.zip', arcdir_path, dir_name, metadata)
            shutil.rmtree(arcdir_path)
            acq_info.append({
                    'path': arcdir_path+'.zip',
                    'prefix': name_prefix,
                    'log_info': '%s%s' % (_id, '.' + acq_no if acq_no is not None else ''),
                    })
        return acq_info


    class DicomFile(object):

        def __init__(self, filepath, anonymize=False):
            dcm = dicom.read_file(filepath, stop_before_pixels=(not anonymize))
            acq_datetime = scidcm.timestamp(dcm.get('AcquisitionDate'), dcm.get('AcquisitionTime'))
            study_datetime = scidcm.timestamp(dcm.get('StudyDate'), dcm.get('StudyTime'))
            self.timestamp = acq_datetime or study_datetime
            self.acq_no = str(dcm.get('AcquisitionNumber', '')) or None if dcm.get('Manufacturer').upper() != 'SIEMENS' else None
            self.patient_id = dcm.get('PatientID', '')
            self.firstname_hash = None
            self.lastname_hash = None
            if anonymize:
                firstname, lastname = scidcm.parse_patient_name(dcm.get('PatientName', ''))
                self.firstname_hash = hashlib.sha256(firstname).hexdigest() if firstname else None
                self.lastname_hash = hashlib.sha256(lastname).hexdigest() if lastname else None
                if dcm.get('PatientBirthDate'):
                    dob = datetime.datetime.strptime(dcm.PatientBirthDate, '%Y%m%d')
                    months = 12 * (study_datetime.year - dob.year) + (study_datetime.month - dob.month) - (study_datetime.day < dob.day)
                    dcm.PatientAge = '%03dM' % months if months < 960 else '%03dY' % (months/12)
                    del dcm.PatientBirthDate
                if dcm.get('PatientName'):
                    del dcm.PatientName
                dcm.save_as(filepath)

def main():
    positional_args = [
        (('host',), dict(help='remote hostname or IP')),
        (('port',), dict(help='remote port')),
        (('return_port',), dict(help='local return port')),
        (('aet',), dict(help='local AE title')),
        (('aec',), dict(help='remote AE title')),
    ]
    optional_args = [
        (('-A', '--no-anonymize'), dict(dest='anonymize', action='store_false', help='do not anonymize patient name and birthdate')),
        (('-b', '--blacklist'), dict(default='discard', help='space-separated list of identifiers to discard ["discard"]')),
        (('-w', '--whitelist'), dict(default='*', help='glob for identifiers to reap ["*"]')),
    ]
    reaper.main(DicomNetReaper, positional_args, optional_args)

if __name__ == '__main__':
    main()
