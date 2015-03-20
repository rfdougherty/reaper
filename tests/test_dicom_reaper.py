import os
import unittest
import subprocess
import time

from scitran.reaper import dicom_reaper

class TestDicomReaper(unittest.TestCase):
    def setUp(self):
        self.db_dir = '/Users/ryan/src/flywheel/reaper/tests/data/common'
        if not os.path.exists(self.db_dir):
            os.mkdir(self.db_dir)
        cmd = ['dcmqrscp', '-v', '-c', 'dcmqrscp.cfg']
        self.dcmqrscp = subprocess.Popen(cmd,
                cwd='/Users/ryan/src/flywheel/reaper/tests/data/',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        time.sleep(20)


    def tearDown(self):
        self.dcmqrscp.kill()
        shutil.rmtree(self.db_dir)

    def test_query(self):
        pass
        #self.assertEqual(db.database_name(), u'Documents')

if __name__ == '__main__':
    unittest.main()
