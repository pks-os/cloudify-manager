########
# Copyright (c) 2019 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import time
from integration_tests import AgentlessTestCase
from integration_tests.tests.utils import get_resource as resource


class TestTaskResume(AgentlessTestCase):

    def test_resumable_mgmtworker_op(self):
        dsl_path = resource("dsl/resumable_mgmtworker.yaml")
        deployment = self.deploy(dsl_path)
        execution = self.execute_workflow(
            workflow_name='execute_operation',
            wait_for_execution=False,
            deployment_id=deployment.id,
            parameters={'operation': 'interface1.op1'})
        while True:
            logs = self.client.events.list(
                execution_id=execution.id, include_logs=True)
            if any('WAITING FOR FILE' in log['message'] for log in logs):
                break
            time.sleep(1)
        self.execute_on_manager('systemctl stop cloudify-mgmtworker')
        self.execute_on_manager('touch /tmp/continue_test')
        self.execute_on_manager('systemctl start cloudify-mgmtworker')
        while True:
            print 'waiting for exec'
            new_exec = self.client.executions.get(execution.id)
            print 'status', new_exec.status
            if new_exec.status == 'terminated':
                break
            time.sleep(1)
