# -*- coding: utf-8 -*-
import os
import time
import unittest
from unittest.mock import create_autospec
from configparser import ConfigParser

from sample_uploader.sample_uploaderServer import MethodContext
from sample_uploader.authclient import KBaseAuth as _KBaseAuth
from sample_uploader.utils.sample_utils import get_sample_service_url, get_sample
from installed_clients.WorkspaceClient import Workspace
from installed_clients.DataFileUtilClient import DataFileUtil

from sample_uploader.utils.misc_utils import get_workspace_user_perms
from sample_uploader.utils.sample_utils import SampleSet


class sample_uploader_unit_tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token = os.environ.get('KB_AUTH_TOKEN', None)
        config_file = os.environ.get('KB_DEPLOYMENT_CONFIG', None)
        cls.cfg = {}
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items('sample_uploader'):
            cls.cfg[nameval[0]] = nameval[1]
        # Getting username from Auth profile for token
        authServiceUrl = cls.cfg['auth-service-url']
        auth_client = _KBaseAuth(authServiceUrl)
        cls.user_id = auth_client.get_user(cls.token)
        # WARNING: don't call any logging methods on the context object,
        # it'll result in a NoneType error
        cls.ctx = MethodContext(None)
        cls.ctx.update({'token': cls.token,
                        'user_id': cls.user_id,
                        'provenance': [
                            {'service': 'sample_uploader',
                             'method': 'please_never_use_it_in_production',
                             'method_params': []
                             }],
                        'authenticated': 1})
        cls.wsURL = cls.cfg['workspace-url']
        cls.wsClient = Workspace(cls.wsURL, token=cls.token)
        cls.curr_dir = os.path.dirname(os.path.realpath(__file__))
        cls.scratch = cls.cfg['scratch']
        cls.wiz_url = cls.cfg['srv-wiz-url']
        cls.sample_url = get_sample_service_url(cls.wiz_url)
        cls.callback_url = os.environ['SDK_CALLBACK_URL']
        suffix = int(time.time() * 1000)
        cls.wsName = "test_ContigFilter_" + str(suffix)
        ret = cls.wsClient.create_workspace({'workspace': cls.wsName})  # noqa
        cls.wsID = ret[0]

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            cls.wsClient.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

    # @unittest.skip('x')
    def test_get_workspace_user_perms(self):
        acls = {
            "read": [],
            "write": [],
            "admin": [],
            "public_read": -1  # set to false (<0)
        }
        self.wsClient.set_permissions({
            "id": self.wsID,
            "new_permission": "w",
            "users": ["jrbolton"]
        })
        ret = get_workspace_user_perms(self.wsURL, self.wsID, self.token, self.user_id, acls)
        self.assertTrue('jrbolton' in ret['write'])
        self.wsClient.set_global_permission({
            "id": self.wsID,
            "new_permission": "r",
        })
        ret = get_workspace_user_perms(self.wsURL, self.wsID, self.token, self.user_id, acls)
        self.assertTrue(ret['public_read'] == 1)

    
    def test_SampleSet_class(self):
        dfu = create_autospec(DataFileUtil, spec_set=True, instance=True)
        ret = {
            'data': [
                {
                    'data': {
                        'description': 'mock',
                        'samples': [
                            {
                                'id': 'id0',
                                'name': 'name0',
                                'version': 'version0',
                            }, {
                                'id': 'id1',
                                'name': 'name1',
                                'version': 'version1',
                            }, {
                                'id': 'id2',
                                'name': 'name2',
                                'version': 'version2',
                            },
                        ],
                    },
                    'info': [
                        -1,
                        'ss_name',
                    ]
                }
            ]
            
        }
        dfu.get_objects = lambda p: ret
        sample_set = SampleSet(dfu, '-1/-2/-3')
        assert sample_set.get_sample_info('name0') == ('name0', 'version0', 'id0')
        assert sample_set.get_sample_info('name1') == ('name1', 'version1', 'id1')
        assert sample_set.get_sample_info('name2') == ('name2', 'version2', 'id2')
        with self.assertRaises(KeyError): sample_set.get_sample_info('blah')

