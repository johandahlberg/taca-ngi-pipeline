""" Unit tests for the deliver commands """

import mock
import os
import shutil
import tempfile
import unittest
from ngi_pipeline.database import classes as db
from taca_ngi_pipeline.deliver import deliver
from taca.utils.transfer import SymlinkError, SymlinkAgent

SAMPLECFG = {
    'deliver': {
        'analysispath': '_ROOTDIR_/ANALYSIS',
        'datapath': '_ROOTDIR_/DATA',
        'stagingpath': '_ROOTDIR_/STAGING',
        'delivery_folder': '_ROOTDIR_/DELIVERY_DESTINATION',
        'operator': 'operator@domain.com',
        'files_to_deliver': [
            ['_ANALYSISPATH_/level0_folder?_file*',
            '_STAGINGPATH_'],
            ['_ANALYSISPATH_/level1_folder2',
            '_STAGINGPATH_'],
            ['_ANALYSISPATH_/*folder0/*/*_file?',
            '_STAGINGPATH_'],
            ['_ANALYSISPATH_/*/_SAMPLEID__folder?_file0',
            '_STAGINGPATH_'],
            ['_ANALYSISPATH_/*/*/this-file-does-not-exist',
            '_STAGINGPATH_'],
            ['_ANALYSISPATH_/level0_folder0_file0',
            '_STAGINGPATH_'],
            ['_DATAPATH_/level1_folder1/level2_folder1/level3_folder1',
            '_STAGINGPATH_'],
        ]}}

class TestDeliverer(unittest.TestCase):  
     
    @classmethod
    def setUpClass(self):
        self.nfolders = 3
        self.nfiles = 3
        self.nlevels = 3
        self.rootdir = tempfile.mkdtemp(prefix="test_taca_deliver_")
        
    @classmethod
    def tearDownClass(self):
        shutil.rmtree(self.rootdir)
    
    @mock.patch.object(deliver.Deliverer,'dbcon',autospec=db.CharonSession)
    def setUp(self,dbmock):
        self.casedir = tempfile.mkdtemp(prefix="case_",dir=self.rootdir)
        self.projectid = 'NGIU-P001'
        self.sampleid = 'NGIU-S001'
        self.dbmock = dbmock
        self.deliverer = deliver.Deliverer(
            self.projectid,
            self.sampleid,
            rootdir=self.casedir,
            **SAMPLECFG['deliver'])
        self.create_content(
            self.deliverer.expand_path(self.deliverer.analysispath))
        self.create_content(
            self.deliverer.expand_path(self.deliverer.datapath))
        
    def tearDown(self):
        try:
            shutil.rmtree(self.casedir)
        except:
            pass
            
    @classmethod
    def create_content(self,parentdir,level=0,folder=0):
        if not os.path.exists(parentdir):
            os.mkdir(parentdir)
        for nf in xrange(self.nfiles):
            open(
                os.path.join(
                    parentdir,
                    "level{}_folder{}_file{}".format(level,folder,nf)),
                'w').close()
        if level == self.nlevels:
            return
        level = level+1
        for nd in xrange(self.nfolders):
            self.create_content(
                os.path.join(
                    parentdir,
                    "level{}_folder{}".format(level,nd)),
                level,
                nd)
    
    @mock.patch.object(
        deliver.db.CharonSession,'sample_get',return_value="mocked return value")
    def test_fetch_sample_db_entry(self,dbmock):
        """ retrieving sample entry from db and caching result """
        self.assertEquals(
            self.deliverer.sample_entry(),
            "mocked return value")
        dbmock.assert_called_with(self.projectid,self.sampleid)
        dbmock.reset_mock()
        self.assertEquals(
            self.deliverer.sample_entry(),
            "mocked return value")
        self.assertFalse(
            dbmock.called,
            "sample_get method should not have been called for cached result")
    
    def test_update_sample_delivery(self):
        with self.assertRaises(NotImplementedError):
            self.deliverer.update_delivery_status()
        
    @mock.patch.object(
        deliver.db.CharonSession,
        'project_create',
        return_value="mocked return value")
    def test_wrap_database_query(self,dbmock):
        self.assertEqual(
            self.deliverer.wrap_database_query(
                self.deliverer.dbcon().project_create,
                "funarg1",
                funarg2="funarg2"),
            "mocked return value")
        dbmock.assert_called_with(
            "funarg1",
            funarg2="funarg2")
        dbmock.side_effect = db.CharonError("mocked error")
        with self.assertRaises(deliver.DelivererDatabaseError):
            self.deliverer.wrap_database_query(
                self.deliverer.dbcon().project_create,
                "funarg1",
                funarg2="funarg2")
        
    def test_gather_files1(self):
        """ Gather files in the top directory """
        expected = [
            os.path.join(
                self.deliverer.expand_path(self.deliverer.analysispath),
                "level0_folder0_file{}".format(n)) \
            for n in xrange(self.nfiles)]
        pattern = SAMPLECFG['deliver']['files_to_deliver'][0]
        self.deliverer.files_to_deliver = [pattern]
        self.assertItemsEqual(
            [p for p,_,_ in self.deliverer.gather_files()],
            expected)
            
    def test_gather_files2(self):
        """ Gather a folder in the top directory """
        expected = [os.path.join(d,f) for d,_,files in os.walk(
            os.path.join(
                self.deliverer.expand_path(self.deliverer.analysispath),
                "level1_folder2")) for f in files]
        pattern = SAMPLECFG['deliver']['files_to_deliver'][1]
        self.deliverer.files_to_deliver = [pattern]
        self.assertItemsEqual(
            [p for p,_,_ in self.deliverer.gather_files()],
            expected)
        
    def test_gather_files3(self):
        """ Gather the files two levels down """
        expected = ["level2_folder{}_file{}".format(m,n) 
                    for m in xrange(self.nfolders) 
                    for n in xrange(self.nfiles)]
        pattern = SAMPLECFG['deliver']['files_to_deliver'][2]
        self.deliverer.files_to_deliver = [pattern]
        self.assertItemsEqual(
            [os.path.basename(p) for p,_,_ in self.deliverer.gather_files()],
            expected)
            
        
    def test_gather_files4(self):
        """ Replace the SAMPLE keyword in pattern """
        expected = ["level1_folder{}_file0".format(n) 
                    for n in xrange(self.nfolders)]
        pattern = SAMPLECFG['deliver']['files_to_deliver'][3]
        self.deliverer.files_to_deliver = [pattern]
        self.deliverer.sampleid = "level1"
        self.assertItemsEqual(
            [os.path.basename(p) for p,_,_ in self.deliverer.gather_files()],
            expected)
            
        
    def test_gather_files5(self):
        """ Do not pick up non-existing file """
        expected = []
        pattern = SAMPLECFG['deliver']['files_to_deliver'][4]
        self.deliverer.files_to_deliver = [pattern]
        self.assertItemsEqual(
            [os.path.basename(p) for p,_,_ in self.deliverer.gather_files()],
            expected)
        
    def test_gather_files7(self):
        """ Traverse folders also if they are symlinks """
        dest_path = self.deliverer.expand_path(
            os.path.join(
                self.deliverer.datapath,
                "level1_folder1",
                "level2_folder1",
                "level3_folder1"))
        sa = SymlinkAgent(
            src_path=self.deliverer.expand_path(
                os.path.join(
                    self.deliverer.analysispath,
                    "level1_folder0",
                    "level2_folder0",
                    "level3_folder0")),
            dest_path=os.path.join(dest_path,"level3_folder0"),
            relative=False)
        self.assertTrue(
            sa.transfer(),
            "failed when setting up test")
        
        expected = [os.path.join(dest_path,"level3_folder1_file{}".format(n)) 
                    for n in xrange(self.nfiles)]
        expected.extend([
            os.path.join(
                dest_path,
                "level3_folder0",
                "level3_folder0_file{}".format(n)) 
                    for n in xrange(self.nfiles)])
        pattern = SAMPLECFG['deliver']['files_to_deliver'][6]
        self.deliverer.files_to_deliver = [pattern]
        self.assertItemsEqual(
            [p for p,_,_ in self.deliverer.gather_files()],
            expected)
    
    def test_stage_delivery1(self):
        """ The correct folder structure should be created and exceptions 
            handled gracefully
        """
        gathered_files = (
            os.path.join(
                self.deliverer.expand_path(self.deliverer.analysispath),
                "level1_folder1",
                "level2_folder0",
                "level2_folder0_file1"),
            os.path.join(
                self.deliverer.expand_path(self.deliverer.stagingpath),
                "level1_folder1_link",
                "level2_folder0_link",
                "level2_folder0_file1_link"),
            "this-is-the-file-hash")
        with mock.patch.object(deliver,'create_folder',return_value=False):
            with self.assertRaises(deliver.DelivererError):
                self.deliverer.stage_delivery()
        with mock.patch.object(
            deliver.Deliverer,'gather_files',return_value=[gathered_files]):
            self.deliverer.stage_delivery()
            expected = os.path.join(
                self.deliverer.expand_path(self.deliverer.stagingpath),
                gathered_files[1])
            self.assertTrue(
                os.path.exists(expected),
                "Expected staged file does not exist")
            self.assertTrue(
                os.path.islink(expected),
                "Staged file is not a link")
            self.assertTrue(
                os.path.exists(self.deliverer.staging_digestfile()),
                "Digestfile does not exist in staging directory")
            with mock.patch.object(
                deliver.transfer.SymlinkAgent,
                'transfer',
                side_effect=SymlinkError("mocked error")):
                self.assertTrue(self.deliverer.stage_delivery())
    
    def test_stage_delivery2(self):
        """ A single file should be staged correctly
        """
        pattern = SAMPLECFG['deliver']['files_to_deliver'][5]
        expected = os.path.join(
            self.deliverer.expand_path(self.deliverer.stagingpath),
            "level0_folder0_file0")
        self.deliverer.files_to_deliver = [pattern]
        self.deliverer.stage_delivery()
        self.assertTrue(os.path.exists(expected),
            "The expected file was not staged")
    
    def test_stage_delivery3(self):
        """ Stage a folder and its subfolders in the top directory """
        expected = [
            os.path.join(
                self.deliverer.expand_path(self.deliverer.stagingpath),
                os.path.relpath(
                    os.path.join(d,f),
                    self.deliverer.expand_path(self.deliverer.analysispath))) \
                for d,_,files in os.walk(
                    os.path.join(
                        self.deliverer.expand_path(self.deliverer.analysispath),
                        "level1_folder2")) \
                for f in files]
        pattern = SAMPLECFG['deliver']['files_to_deliver'][1]
        self.deliverer.files_to_deliver = [pattern]
        self.deliverer.stage_delivery()
        self.assertItemsEqual(
            [os.path.exists(e) for e in expected],
            [True for i in xrange(len(expected))])
    
    def test_expand_path(self):
        """ Paths should expand correctly """
        cases = [
            ["this-path-should-not-be-touched",
            "this-path-should-not-be-touched",
            "a path without placeholders was modified"],
            ["this-path-_SHOULD_-be-touched",
            "this-path-was-to-be-touched",
            "a path with placeholders was not correctly modified"],
            ["this-path-_SHOULD_-be-touched-_MULTIPLE_",
            "this-path-was-to-be-touched-twice",
            "a path with multiple placeholders was not correctly modified"],
            ["this-path-should-_not_-be-touched",
            "this-path-should-_not_-be-touched",
            "a path without valid placeholders was modified"],
            [None,None,"a None path should be handled without exceptions"]]
        self.deliverer.should = 'was-to'
        self.deliverer.multiple = 'twice'
        for case, exp, msg in cases:
            self.assertEqual(self.deliverer.expand_path(case),exp,msg)
        with self.assertRaises(deliver.DelivererError):
            self.deliverer.expand_path("this-path-_WONT_-be-touched")

class TestProjectDeliverer(unittest.TestCase):  
    
    @classmethod
    def setUpClass(self):
        self.rootdir = tempfile.mkdtemp(prefix="test_taca_deliver_")
        
    @classmethod
    def tearDownClass(self):
        shutil.rmtree(self.rootdir)
    
    @mock.patch.object(deliver.Deliverer,'dbcon',autospec=db.CharonSession)
    def setUp(self,dbmock):
        self.casedir = tempfile.mkdtemp(prefix="case_",dir=self.rootdir)
        self.projectid = 'NGIU-P001'
        self.deliverer = deliver.ProjectDeliverer(
            self.projectid,
            rootdir=self.casedir,
            **SAMPLECFG['deliver'])
        
    def tearDown(self):
        shutil.rmtree(self.casedir)
        
    def test_init(self):
        """ A ProjectDeliverer should initiate properly """
        self.assertIsInstance(
            getattr(self,'deliverer'),
            deliver.ProjectDeliverer)
    
    @mock.patch.object(
        deliver.db.CharonSession,
        'project_update',
        return_value="mocked return value")
    def test_update_delivery_status(self,dbmock):
        """ Updating the delivery status for a project """
        self.assertEquals(
            self.deliverer.update_delivery_status(),
            "mocked return value")
        dbmock.assert_called_with(
            self.projectid,
            delivery_status="DELIVERED")

class TestSampleDeliverer(unittest.TestCase):  
    
    @classmethod
    def setUpClass(self):
        self.rootdir = tempfile.mkdtemp(prefix="test_taca_deliver_")
        
    @classmethod
    def tearDownClass(self):
        shutil.rmtree(self.rootdir)
    
    @mock.patch.object(deliver.Deliverer,'dbcon',autospec=db.CharonSession)
    def setUp(self,dbmock):
        self.casedir = tempfile.mkdtemp(prefix="case_",dir=self.rootdir)
        self.projectid = 'NGIU-P001'
        self.sampleid = 'NGIU-S001'
        self.deliverer = deliver.SampleDeliverer(
            self.projectid,
            self.sampleid,
            rootdir=self.casedir,
            **SAMPLECFG['deliver'])
            
    def tearDown(self):
        shutil.rmtree(self.casedir)
    
    def test_init(self):
        """ A SampleDeliverer should initiate properly """
        self.assertIsInstance(
            getattr(self,'deliverer'),
            deliver.SampleDeliverer)
    
    @mock.patch.object(
        deliver.db.CharonSession,
        'sample_update',
        return_value="mocked return value")
    def test_update_delivery_status(self,dbmock):
        """ Updating the delivery status for a sample """
        self.assertEquals(
            self.deliverer.update_delivery_status(),
            "mocked return value")
        dbmock.assert_called_with(
            self.projectid,
            self.sampleid,
            delivery_status="DELIVERED")
        
