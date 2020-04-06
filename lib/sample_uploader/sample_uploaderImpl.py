# -*- coding: utf-8 -*-
#BEGIN_HEADER
import logging
import os
import json
import uuid
import shutil

from installed_clients.KBaseReportClient import KBaseReport
from installed_clients.DataFileUtilClient import DataFileUtil
from .utils.importer import import_samples_from_file
from .utils.mappings import SESAR_mappings, ENIGMA_mappings
from .utils.sample_utils import (
    sample_set_to_OTU_sheet,
    update_acls,
    get_sample_service_url
)
#END_HEADER


class sample_uploader:
    '''
    Module Name:
    sample_uploader

    Module Description:
    A KBase module: sample_uploader
    '''

    ######## WARNING FOR GEVENT USERS ####### noqa
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    ######################################### noqa
    VERSION = "0.0.4"
    GIT_URL = "https://github.com/kbaseapps/sample_uploader"
    GIT_COMMIT_HASH = "9bc612605a1f39b01270ca0870b00c9a97f67db4"

    #BEGIN_CLASS_HEADER
    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.callback_url = os.environ['SDK_CALLBACK_URL']
        self.scratch = config['scratch']
        # janky, but works for now
        self.sw_url = config.get('kbase-endpoint') + '/service_wizard'
        self.dfu = DataFileUtil(url=self.callback_url)
        logging.basicConfig(format='%(created)s %(levelname)s: %(message)s',
                            level=logging.INFO)
        #END_CONSTRUCTOR
        pass


    def import_samples(self, ctx, params):
        """
        :param params: instance of type "ImportSampleInputs" -> structure:
           parameter "sample_file" of String, parameter "workspace_name" of
           String, parameter "workspace_id" of Long, parameter "file_format"
           of String, parameter "description" of String, parameter "set_name"
           of String, parameter "output_format" of String, parameter
           "taxonomy_source" of String, parameter "num_otus" of Long,
           parameter "incl_seq" of Long, parameter "otu_prefix" of String
        :returns: instance of type "ImportSampleOutputs" -> structure:
           parameter "report_name" of String, parameter "report_ref" of
           String, parameter "sample_set" of type "SampleSet" -> structure:
           parameter "samples" of list of type "sample_info" -> structure:
           parameter "id" of type "sample_id", parameter "name" of String,
           parameter "description" of String, parameter "sample_set_ref" of
           String
        """
        # ctx is the context object
        # return variables are: output
        #BEGIN import_samples
        set_name = params.get("set_name")
        if params.get('file_format') == 'ENIGMA':
            sample_set = import_samples_from_file(
                params,
                self.sw_url,
                ctx['token'],
                ENIGMA_mappings['verification_mapping'],
                ENIGMA_mappings['cols_mapping'],
                ENIGMA_mappings.get('groups'),
                ENIGMA_mappings['date_cols'],
                ENIGMA_mappings.get('column_unit_regex'),
                header_index=0
            )
        elif params.get('file_format') == 'SESAR':
            sample_set = import_samples_from_file(
                params,
                self.sw_url,
                ctx['token'],
                SESAR_mappings['verification_mapping'],
                SESAR_mappings['cols_mapping'],
                SESAR_mappings.get('groups'),
                SESAR_mappings['date_cols'],
                SESAR_mappings.get('column_unit_regex'),
                header_index=1
            )
        else:
            raise ValueError(f"Only SESAR and ENIGMA formats are currently supported for importing samples.")
        
        obj_info = self.dfu.save_objects({
            'id': params.get('workspace_id'),
            'objects': [{
                "type": "KBaseSets.SampleSet",
                "data": sample_set,
                "name": set_name
            }]
        })[0]
        sample_set_ref = '/'.join([str(obj_info[6]), str(obj_info[0]), str(obj_info[4])])
        sample_file_name = os.path.basename(params['sample_file']).split('.')[0] + '_OTU'

        if params.get('output_format') in ['csv', 'xls']:
            otu_path = sample_set_to_OTU_sheet(
                sample_set,
                sample_file_name,
                self.scratch,
                params
            )
            file_links = [{
                'path': otu_path,
                'name': os.path.basename(otu_path),
                'label': "OTU template file",
                'description': "file with each column containing the assigned sample_id and sample "
                               "name of each saved sample. Intended for uploading OTU data."
            }]
        else:
            file_links = []

        if params.get('incl_input_in_output'):
            sample_file = params.get('sample_file')
            if not os.path.isfile(sample_file):
                # try prepending '/staging/' to file and check then
                if os.path.isfile(os.path.join('/staging', sample_file)):
                    sample_file = os.path.join('/staging', sample_file)
                else:
                    raise ValueError(f"input file {sample_file} does not exist.")
            sample_file_copy = os.path.join(self.scratch, os.path.basename(sample_file))
            shutil.copy(sample_file, sample_file_copy)
            file_links.append({
                "path": sample_file_copy,
                "name": os.path.basename(sample_file_copy),
                "label": "Input Sample file",
                "description": "Input file provided to create the sample set."
            })

        # create report
        report_client = KBaseReport(self.callback_url)
        report_name = "SampleSet_import_report_" + str(uuid.uuid4())
        report_info = report_client.create_extended_report({
            'message': f"SampleSet object named \"{set_name}\" imported.",
            'objects_created': [{'ref': sample_set_ref}],
            'file_links': file_links,
            'report_object_name': report_name,
            'workspace_name': params['workspace_name']
        })
        output = {
            'report_ref': report_info['ref'],
            'report_name': report_info['name'],
            'sample_set': sample_set,
            'sample_set_ref': sample_set_ref
        }

        #END import_samples

        # At some point might do deeper type checking...
        if not isinstance(output, dict):
            raise ValueError('Method import_samples return value ' +
                             'output is not type dict as required.')
        # return the results
        return [output]

    def generate_OTU_sheet(self, ctx, params):
        """
        :param params: instance of type "GenerateOTUSheetParams" (Generate a
           customized OTU worksheet using a SampleSet input to generate the
           appropriate columns.) -> structure: parameter "workspace_name" of
           String, parameter "workspace_id" of Long, parameter
           "sample_set_ref" of String, parameter "output_name" of String,
           parameter "output_format" of String, parameter "num_otus" of Long,
           parameter "taxonomy_source" of String, parameter "incl_seq" of
           Long, parameter "otu_prefix" of String
        :returns: instance of type "GenerateOTUSheetOutputs" -> structure:
           parameter "report_name" of String, parameter "report_ref" of String
        """
        # ctx is the context object
        # return variables are: output
        #BEGIN generate_OTU_sheet
        # first we download sampleset
        sample_set_ref = params.get('sample_set_ref')
        ret = self.dfu.get_objects({'object_refs': [sample_set_ref]})['data'][0]
        sample_set = ret['data']
        if params.get('output_name'):
            output_name = params.get('output_name')
        else:
            # if output_name not specified use name of sample_set as output + "_OTUs"
            output_name = ret['info'][1] + "_OTUs"
        otu_path = sample_set_to_OTU_sheet(
            sample_set,
            output_name,
            self.scratch,
            params
        )
        report_client = KBaseReport(self.callback_url)
        report_name = "Generate_OTU_sheet_report_" + str(uuid.uuid4())
        report_info = report_client.create_extended_report({
            'file_links': [{
                'path': otu_path,
                'name': os.path.basename(otu_path),
                'label': "CSV with headers for OTU",
                'description': "CSV file with each column containing the assigned sample_id and sample "
                               "name of each saved sample. Intended for uploading OTU data."
            }],
            'report_object_name': report_name,
            'workspace_name': params['workspace_name']
        })
        output = {
            'report_ref': report_info['ref'],
            'report_name': report_info['name'],
        }

        #END generate_OTU_sheet

        # At some point might do deeper type checking...
        if not isinstance(output, dict):
            raise ValueError('Method generate_OTU_sheet return value ' +
                             'output is not type dict as required.')
        # return the results
        return [output]

    def update_sample_set_acls(self, ctx, params):
        """
        :param params: instance of type "update_sample_set_acls_params" ->
           structure: parameter "sample_set_ref" of String, parameter
           "new_users" of list of String, parameter "is_reader" of Long,
           parameter "is_writer" of Long, parameter "is_admin" of Long
        :returns: instance of type "update_sample_set_acls_output" ->
           structure: parameter "status" of String
        """
        # ctx is the context object
        # return variables are: output
        #BEGIN update_sample_set_acls

        # first get sample_set object
        sample_set_ref = params.get('sample_set_ref')
        ret = self.dfu.get_objects({'object_refs': [sample_set_ref]})['data'][0]
        sample_set = ret['data']
        sample_url = get_sample_service_url(self.sw_url)

        acls = {
            'reader': [],
            'writer': [],
            'admin': []
        }
        for new_user in params.get('new_users'):
            if params.get('is_admin'):
                acls['admin'].append(new_user)
            elif params.get('is_writer'):
                acls['writer'].append(new_user)
            elif params.get('is_reader'):
                acls['reader'].append(new_user)

        for sample in sample_set['samples']:
            sample_id = sample['id']
            status = update_acls(sample_url, sample_id, acls, ctx['token'])
        output = {"status": status}
        #END update_sample_set_acls

        # At some point might do deeper type checking...
        if not isinstance(output, dict):
            raise ValueError('Method update_sample_set_acls return value ' +
                             'output is not type dict as required.')
        # return the results
        return [output]
    def status(self, ctx):
        #BEGIN_STATUS
        returnVal = {'state': "OK",
                     'message': "",
                     'version': self.VERSION,
                     'git_url': self.GIT_URL,
                     'git_commit_hash': self.GIT_COMMIT_HASH}
        #END_STATUS
        return [returnVal]
