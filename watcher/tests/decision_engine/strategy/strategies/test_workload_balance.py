# -*- encoding: utf-8 -*-
# Copyright (c) 2016 Intel Corp
#
# Authors: Junjie-Huang <junjie.huang@intel.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import collections
import mock

from watcher.applier.actions.loading import default
from watcher.common import exception
from watcher.decision_engine.model import model_root
from watcher.decision_engine.model import resource
from watcher.decision_engine.strategy.strategies import workload_balance
from watcher.tests import base
from watcher.tests.decision_engine.strategy.strategies \
    import faker_cluster_state
from watcher.tests.decision_engine.strategy.strategies \
    import faker_metrics_collector


class TestWorkloadBalance(base.BaseTestCase):
    # fake metrics
    fake_metrics = faker_metrics_collector.FakerMetricsCollector()

    # fake cluster
    fake_cluster = faker_cluster_state.FakerModelCollector()

    def test_calc_used_res(self):
        model = self.fake_cluster.generate_scenario_6_with_2_hypervisors()
        strategy = workload_balance.WorkloadBalance()
        hypervisor = model.get_hypervisor_from_id('Node_0')
        cap_cores = model.get_resource_from_id(resource.ResourceType.cpu_cores)
        cap_mem = model.get_resource_from_id(resource.ResourceType.memory)
        cap_disk = model.get_resource_from_id(resource.ResourceType.disk)
        cores_used, mem_used, disk_used = strategy.calculate_used_resource(
            model, hypervisor, cap_cores, cap_mem, cap_disk)

        self.assertEqual((cores_used, mem_used, disk_used), (20, 4, 40))

    def test_group_hosts_by_cpu_util(self):
        model = self.fake_cluster.generate_scenario_6_with_2_hypervisors()
        strategy = workload_balance.WorkloadBalance()
        strategy.threshold = 30
        strategy.ceilometer = mock.MagicMock(
            statistic_aggregation=self.fake_metrics.mock_get_statistics_wb)
        h1, h2, avg, w_map = strategy.group_hosts_by_cpu_util(model)
        # print h1, h2, avg, w_map
        self.assertEqual(h1[0]['hv'].uuid, 'Node_0')
        self.assertEqual(h2[0]['hv'].uuid, 'Node_1')
        self.assertEqual(avg, 8.0)

    def test_choose_vm_to_migrate(self):
        model = self.fake_cluster.generate_scenario_6_with_2_hypervisors()
        strategy = workload_balance.WorkloadBalance()
        strategy.ceilometer = mock.MagicMock(
            statistic_aggregation=self.fake_metrics.mock_get_statistics_wb)
        h1, h2, avg, w_map = strategy.group_hosts_by_cpu_util(model)
        vm_to_mig = strategy.choose_vm_to_migrate(model, h1, avg, w_map)
        self.assertEqual(vm_to_mig[0].uuid, 'Node_0')
        self.assertEqual(vm_to_mig[1].uuid,
                         "73b09e16-35b7-4922-804e-e8f5d9b740fc")

    def test_choose_vm_notfound(self):
        model = self.fake_cluster.generate_scenario_6_with_2_hypervisors()
        strategy = workload_balance.WorkloadBalance()
        strategy.ceilometer = mock.MagicMock(
            statistic_aggregation=self.fake_metrics.mock_get_statistics_wb)
        h1, h2, avg, w_map = strategy.group_hosts_by_cpu_util(model)
        vms = model.get_all_vms()
        vms.clear()
        vm_to_mig = strategy.choose_vm_to_migrate(model, h1, avg, w_map)
        self.assertEqual(vm_to_mig, None)

    def test_filter_destination_hosts(self):
        model = self.fake_cluster.generate_scenario_6_with_2_hypervisors()
        strategy = workload_balance.WorkloadBalance()
        strategy.ceilometer = mock.MagicMock(
            statistic_aggregation=self.fake_metrics.mock_get_statistics_wb)
        h1, h2, avg, w_map = strategy.group_hosts_by_cpu_util(model)
        vm_to_mig = strategy.choose_vm_to_migrate(model, h1, avg, w_map)
        dest_hosts = strategy.filter_destination_hosts(model, h2, vm_to_mig[1],
                                                       avg, w_map)
        self.assertEqual(len(dest_hosts), 1)
        self.assertEqual(dest_hosts[0]['hv'].uuid, 'Node_1')

    def test_exception_model(self):
        strategy = workload_balance.WorkloadBalance()
        self.assertRaises(exception.ClusterStateNotDefined, strategy.execute,
                          None)

    def test_exception_cluster_empty(self):
        strategy = workload_balance.WorkloadBalance()
        model = model_root.ModelRoot()
        self.assertRaises(exception.ClusterEmpty, strategy.execute, model)

    def test_execute_cluster_empty(self):
        strategy = workload_balance.WorkloadBalance()
        strategy.ceilometer = mock.MagicMock(
            statistic_aggregation=self.fake_metrics.mock_get_statistics_wb)
        model = model_root.ModelRoot()
        self.assertRaises(exception.ClusterEmpty, strategy.execute, model)

    def test_execute_no_workload(self):
        strategy = workload_balance.WorkloadBalance()
        strategy.ceilometer = mock.MagicMock(
            statistic_aggregation=self.fake_metrics.mock_get_statistics_wb)

        current_state_cluster = faker_cluster_state.FakerModelCollector()
        model = current_state_cluster. \
            generate_scenario_4_with_1_hypervisor_no_vm()

        solution = strategy.execute(model)
        self.assertEqual(solution.actions, [])

    def test_execute(self):
        strategy = workload_balance.WorkloadBalance()
        strategy.ceilometer = mock.MagicMock(
            statistic_aggregation=self.fake_metrics.mock_get_statistics_wb)
        model = self.fake_cluster.generate_scenario_6_with_2_hypervisors()
        solution = strategy.execute(model)
        actions_counter = collections.Counter(
            [action.get('action_type') for action in solution.actions])

        num_migrations = actions_counter.get("migrate", 0)
        self.assertEqual(num_migrations, 1)

    def test_check_parameters(self):
        strategy = workload_balance.WorkloadBalance()
        strategy.ceilometer = mock.MagicMock(
            statistic_aggregation=self.fake_metrics.mock_get_statistics_wb)
        model = self.fake_cluster.generate_scenario_6_with_2_hypervisors()
        solution = strategy.execute(model)
        loader = default.DefaultActionLoader()
        for action in solution.actions:
            loaded_action = loader.load(action['action_type'])
            loaded_action.input_parameters = action['input_parameters']
            loaded_action.validate_parameters()
