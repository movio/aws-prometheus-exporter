# -*- coding: utf-8 -*-

import unittest.mock as mock
from collections import namedtuple

from aws_metrics import AwsMetricsCollector, AwsMetric

# pylint: disable=protected-access

SINGLE_METRIC_YAML = """
ec2_instance_ids:
  description: EC2 instance ids
  type: array_to_unit_gauge
  value_label: instance_id
  service: ec2
  paginator: describe_instances
  filters:
    - Name: instance-state-name
      Values: [ "Running" ]
  search: Reservations[].Instances[].InstanceId
"""

MULTIPLE_METRICS_YAML = """
public_ec2_instance_ids:
  description: EC2 instance ids of instances with a public IP
  type: array_to_unit_gauge
  value_label: instance_id
  service: ec2
  paginator: describe_instances
  filters:
    - Name: instance-state-name
      Values: [ "Running" ]
  search: Reservations[].Instances[?PublicIpAddress][].InstanceId

ssm_agents_ec2_instance_ids:
  description: EC2 instance ids of instances with SSM agent
  type: array_to_unit_gauge
  value_label: instance_id
  service: ssm
  paginator: describe_instance_information
  filters:
    - Key: ResourceType
      Values: [ "EC2Instance" ]
    - Key: PingStatus
      Values: [ "Online" ]
  search: InstanceInformationList[].InstanceId
"""


def test_load_single_aws_metric():
    metrics_scanner = AwsMetricsCollector(SINGLE_METRIC_YAML)
    assert len(metrics_scanner.metrics) == 1
    ec2_instance_ids = metrics_scanner.metrics[0]
    assert ec2_instance_ids == AwsMetric(
        name="ec2_instance_ids",
        description="EC2 instance ids",
        type="array_to_unit_gauge",
        value_label="instance_id",
        service="ec2",
        filters=[{
            "Name": "instance-state-name",
            "Values": ["Running"]
        }],
        paginator="describe_instances",
        search="Reservations[].Instances[].InstanceId"
    )


def test_load_multiple_aws_metrics():
    metrics_scanner = AwsMetricsCollector(MULTIPLE_METRICS_YAML)
    assert len(metrics_scanner.metrics) == 2
    assert metrics_scanner.metrics[0] == AwsMetric(
        name="public_ec2_instance_ids",
        description="EC2 instance ids of instances with a public IP",
        type="array_to_unit_gauge",
        value_label="instance_id",
        service="ec2",
        filters=[{
            "Name": "instance-state-name",
            "Values": ["Running"]
        }],
        paginator="describe_instances",
        search="Reservations[].Instances[?PublicIpAddress][].InstanceId"
    )
    assert metrics_scanner.metrics[1] == AwsMetric(
        name="ssm_agents_ec2_instance_ids",
        description="EC2 instance ids of instances with SSM agent",
        type="array_to_unit_gauge",
        value_label="instance_id",
        service="ssm",
        filters=[
            {
                "Key": "ResourceType",
                "Values": ["EC2Instance"]
            },
            {
                "Key": "PingStatus",
                "Values": ["Online"],
            }
        ],
        paginator="describe_instance_information",
        search="InstanceInformationList[].InstanceId"
    )


SessionMocks = namedtuple("SessionMocks", [
    "session",
    "service",
    "paginator",
    "paginate_response_iterator"
])


def create_session_mocks(search_response_iterator):
    session = mock.NonCallableMagicMock()
    paginator = mock.NonCallableMagicMock()
    service = mock.NonCallableMagicMock()
    paginate_response_iterator = mock.NonCallableMagicMock()
    paginate_response_iterator.search = mock.Mock(return_value=search_response_iterator)
    paginator.paginate = mock.Mock(return_value=paginate_response_iterator)
    service.get_paginator = mock.Mock(return_value=paginator)
    session.client = mock.Mock(return_value=service)
    return SessionMocks(session, service, paginator, paginate_response_iterator)


def test_get_response_iterator():
    response_iterator = iter(["instance_id_1", "instance_id_2", "instance_id_3"])
    mocks = create_session_mocks(response_iterator)
    metrics_collector = AwsMetricsCollector(SINGLE_METRIC_YAML)
    assert response_iterator == metrics_collector._get_response_iterator(mocks.session, metrics_collector.metrics[0])
    mocks.session.client.assert_called_once_with("ec2")
    mocks.service.get_paginator.assert_called_once_with("describe_instances")
    mocks.paginator.paginate.assert_called_once_with(Filters=[{
        "Name": "instance-state-name",
        "Values": ["Running"]
    }])
    mocks.paginate_response_iterator.search.assert_called_once_with("Reservations[].Instances[].InstanceId")


def test_run_array_to_unit_gauge_metric():
    response_iterator = iter(["instance_id_1", "instance_id_2", "instance_id_3"])
    mocks = create_session_mocks(response_iterator)
    metrics_collector = AwsMetricsCollector(SINGLE_METRIC_YAML)
    gauge = metrics_collector._run_array_to_unit_gauge_metric(
        metrics_collector.metrics[0], mocks.session, ["env"], ["test"])
    assert gauge._labelnames == ("env", "instance_id")
    metric_values = {labels: gauge._value._value for labels, gauge in gauge._metrics.items()}
    assert metric_values == {
        ('test', 'instance_id_1'): 1.0,
        ('test', 'instance_id_2'): 1.0,
        ('test', 'instance_id_3'): 1.0
    }
