# =============================================================================
# Copyright [2013] [Kevin Carter]
# License Information :
# This software has no warranty, it is provided 'as is'. It is your
# responsibility to validate the behavior of the routines and its accuracy
# using the code provided. Consult the GNU General Public license for further
# details (see GNU General Public License).
# http://www.gnu.org/licenses/gpl.html
# =============================================================================
import os

from turbolift.clouderator import actions
from turbolift import methods
from turbolift import utils
from turbolift.worker import ARGS
from turbolift.worker import LOG


class upload(object):
    """Setup and run the upload Method."""

    def __init__(self, auth):
        self.auth = auth
        self.go = None
        self.action = None

    def start(self):
        """This is the upload method.

        Uses file_upload is to simply upload all files and folders to a
        specified container.
        """

        # Index Local Files for Upload
        f_indexed = methods.get_local_files()
        num_files = len(f_indexed)

        # Get The rate of concurrency
        concurrency = utils.set_concurrency(args=ARGS, file_count=num_files)

        # Package up the Payload
        payload = utils.prep_payload(
            auth=self.auth,
            container=ARGS.get('container', utils.rand_string()),
            source=utils.get_local_source(args=ARGS),
            args=ARGS
        )

        LOG.info('MESSAGE\t: "%s" Files have been found.', num_files)
        LOG.debug('PAYLOAD\t: "%s"', payload)

        batch_size = utils.batcher(num_files=num_files)
        for work in utils.batch_gen(data=f_indexed,
                                    batch_size=batch_size,
                                    count=num_files):
            work_q = utils.basic_queue(work)
            # Set the actions class up
            self.go = actions.cloud_actions(payload=payload)
            self.go._container_create(url=payload['url'],
                                      container=payload['c_name'])
            with methods.spinner(work_q=work_q):
                utils.worker_proc(job_action=self.uploaderator,
                                  num_jobs=num_files,
                                  concurrency=concurrency,
                                  t_args=payload,
                                  queue=work_q)

        if ARGS.get('delete_remote') is True:
            with methods.spinner(work_q=None):
                self.remote_delete(payload=payload,
                                   f_indexed=f_indexed)

    def uploaderator(self, work_q, payload):
        """Upload files to CloudFiles -Swift-.

        :param work_q:
        :param payload:
        """

        # Get work from the Queue
        while True:
            wfile = utils.get_from_q(queue=work_q)
            # If Work is None return None
            if wfile is None:
                break
            try:
                source = payload['source']
                container = payload['c_name']
                self.go.object_putter(url=payload['url'],
                                      container=container,
                                      source=source,
                                      u_file=wfile)
            except KeyboardInterrupt:
                utils.emergency_kill(reclaim=True)
            except EOFError:
                utils.emergency_kill()

    def remote_delete(self, payload, f_indexed):
        """If Remote Delete was True run.

        NOTE: Remote delete will delete ALL Objects in a remote container
        which differ from the objects in the SOURCED LOCAL FILESYSTEM.

        IE: If this option is used, on one directory and then another directory
        and the files were different any difference would be deleted and based
        on the index information found in LOCAL FILE SYSTEM on the LAST
        command run.

        :return:
        """

        utils.reporter(msg='Getting file list for REMOTE DELETE')
        objects = self.go.object_lister(url=payload['url'],
                                        container=payload['c_name'])
        source = payload['source']
        obj_names = [os.path.join(source, obj.get('name')) for obj in objects]

        # From the remote system see if we have differences in the local system
        _objects = utils.return_diff(target=obj_names, source=f_indexed)

        if _objects:
            # Set Basic Data for file delete.
            _num_files = len(_objects)
            LOG.info('MESSAGE\t: "%s" Files have been found to be removed from'
                     ' the REMOTE CONTAINER.', _num_files)

            _concurrency = utils.set_concurrency(args=ARGS,
                                                 file_count=_num_files)

            # Delete the difference in Files.
            utils.reporter(msg='Performing Remote Delete')
            batch_size = utils.batcher(num_files=_num_files)
            for work in utils.batch_gen(data=_objects,
                                        batch_size=batch_size,
                                        count=_num_files):
                work_q = utils.basic_queue(work)
                utils.worker_proc(job_action=self.deleterator,
                                  num_jobs=_num_files,
                                  concurrency=_concurrency,
                                  t_args=payload,
                                  queue=work_q)
        else:
            utils.reporter(msg='No Difference between REMOTE and LOCAL'
                               ' Directories.')

    def deleterator(self, work_q, payload):
        """Delete files to CloudFiles -Swift-.

        :param work_q:
        :param payload:
        """

        # Get work from the Queue
        while True:
            wfile = utils.get_from_q(queue=work_q)
            # If Work is None return None
            if wfile is None:
                break
            try:
                wfile = utils.get_sfile(ufile=wfile, source=payload['source'])
                self.go.object_deleter(url=payload['url'],
                                       container=payload['c_name'],
                                       u_file=wfile)
            except EOFError:
                utils.emergency_kill()
            except KeyboardInterrupt:
                utils.emergency_kill(reclaim=True)
