# -*- coding: utf-8 -*-

import unittest.mock as mock
from collections import namedtuple

from aws_metrics import _parse_metrics, AwsMetric

# pylint: disable=protected-access

SINGLE_METRIC_YAML = """
ec2_instance_ids:
  description: EC2 instance ids
  service: ec2
  paginator: describe_instances
  paginator_args:
    Filters:
      - Name: instance-state-name
        Values: [ "Running" ]
  search: |
    Reservations[].Instances[].{id: InstanceId, value: `1`}[]
"""

MULTIPLE_METRICS_YAML = """
public_ec2_instance_ids:
  description: EC2 instance ids of instances with a public IP
  service: ec2
  paginator: describe_instances
  paginator_args:
    Filters:
      - Name: instance-state-name
        Values: [ "Running" ]
  search: |
    Reservations[].Instances[?PublicIpAddress].{id: InstanceId, value: `1`}[]

ssm_agents_ec2_instance_ids:
  description: EC2 instance ids of instances with SSM agent
  service: ssm
  paginator: describe_instance_information
  paginator_args:
    Filters:
      - Key: ResourceType
        Values: [ "EC2Instance" ]
      - Key: PingStatus
        Values: [ "Online" ]
  search: |
    InstanceInformationList[].{id: InstanceId, value: `1`}[]
"""


def test_load_single_aws_metric():
    metrics = _parse_metrics(SINGLE_METRIC_YAML)
    assert len(metrics) == 1
    ec2_instance_ids = metrics[0]
    assert ec2_instance_ids == AwsMetric(
        name="ec2_instance_ids",
        description="EC2 instance ids",
        service="ec2",
        paginator="describe_instances",
        paginator_args={
            "Filters": [{
                "Name": "instance-state-name",
                "Values": ["Running"]
            }]
        },
        search="Reservations[].Instances[].{id: InstanceId, value: `1`}[]",
        update_freq_mins=5
    )


def test_load_multiple_aws_metrics():
    metrics = _parse_metrics(MULTIPLE_METRICS_YAML)
    assert len(metrics) == 2
    assert metrics[0] == AwsMetric(
        name="public_ec2_instance_ids",
        description="EC2 instance ids of instances with a public IP",
        service="ec2",
        paginator="describe_instances",
        paginator_args={
          "Filters": [{
            "Name": "instance-state-name",
            "Values": ["Running"]
          }]
        },
        search="Reservations[].Instances[?PublicIpAddress].{id: InstanceId, value: `1`}[]",
        update_freq_mins=5
    )
    assert metrics[1] == AwsMetric(
        name="ssm_agents_ec2_instance_ids",
        description="EC2 instance ids of instances with SSM agent",
        service="ssm",
        paginator_args={
          "Filters": [
            {
                "Key": "ResourceType",
                "Values": ["EC2Instance"]
            },
            {
                "Key": "PingStatus",
                "Values": ["Online"],
            }
          ]
        },
        paginator="describe_instance_information",
        search="InstanceInformationList[].{id: InstanceId, value: `1`}[]",
        update_freq_mins=5
    )
# 
# SessionMocks = namedtuple("SessionMocks", [
#     "session",
#     "service",
#     "paginator",
#     "paginate_response_iterator"
# ])
# 
# 
# def create_session_mocks(search_response_iterator):
#     session = mock.NonCallableMagicMock()
#     paginator = mock.NonCallableMagicMock()
#     service = mock.NonCallableMagicMock()
#     paginate_response_iterator = mock.NonCallableMagicMock()
#     paginate_response_iterator.search = mock.Mock(return_value=search_response_iterator)
#     paginator.paginate = mock.Mock(return_value=paginate_response_iterator)
#     service.get_paginator = mock.Mock(return_value=paginator)
#     session.client = mock.Mock(return_value=service)
#     return SessionMocks(session, service, paginator, paginate_response_iterator)
# 
# 
# def test_get_response_iterator():
#     response_iterator = iter(["instance_id_1", "instance_id_2", "instance_id_3"])
#     mocks = create_session_mocks(response_iterator)
#     metrics_collector = AwsMetricsCollector(SINGLE_METRIC_YAML)
#     assert response_iterator == metrics_collector._get_response_iterator(mocks.session, metrics_collector.metrics[0])
#     mocks.session.client.assert_called_once_with("ec2")
#     mocks.service.get_paginator.assert_called_once_with("describe_instances")
#     mocks.paginator.paginate.assert_called_once_with(Filters=[{
#         "Name": "instance-state-name",
#         "Values": ["Running"]
#     }])
#     mocks.paginate_response_iterator.search.assert_called_once_with("Reservations[].Instances[].{id: InstanceId, value: `1`}[]")
# 
# 
# def test_run_metric():
#     response_iterator = iter([
#         { "id": "instance_id_1", "value": 1},
#         { "id": "instance_id_2", "value": 1},
#         { "id": "instance_id_3", "value": 1}
#     ])
#     mocks = create_session_mocks(response_iterator)
#     metrics_collector = AwsMetricsCollector(SINGLE_METRIC_YAML)
#     gauge = metrics_collector._run_metric(
#         metrics_collector.metrics[0], mocks.session)
#     assert gauge._labelnames == ("id",)
#     metric_values = {labels: gauge._value._value for labels, gauge in gauge._metrics.items()}
#     assert metric_values == {
#         ('instance_id_1',): 1.0,
#         ('instance_id_2',): 1.0,
#         ('instance_id_3',): 1.0
#     }
