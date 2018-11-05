# AWS Prometheus Exporter

This Python module allows you to run AWS API calls through Boto3, and expose the results of those calls as Prometheus metrics.
Metrics must be described in YAML. For example:

```yaml
ec2_instance_ids:
  description: EC2 instance ids
  service: ec2
  paginator: describe_instances
  paginator_args:
    Filters:
      - Name: instance-state-name
        Values: [ "running" ]
  label_names:
    - instance_id
  search: |
    Reservations[].Instances[].{instance_id: InstanceId, value: `1`}
```

The above describes a Prometheus metric derived from calling the following in Boto3:
```python
result = boto3.client("ec2") \
            .get_paginator("describe_instances") \
            .paginate({"Filters": [{"Name": "instance-state-name", "Values": ["running"]}]}) \
            .search("Reservations[].Instances[].{instance_id: InstanceId, value: `1`}")
```

You aren't restricted to calling paginators. By specifying `method` and `method_args` in place of `paginator` and `paginator_args`, you can call any service method. Pagination will be handled for you in the following fashion:

```python
  service = boto3.client("ec2")
  next_token = ''
  result = []
  kwargs = {"Filters": [{"Name": "instance-state-name", "Values": ["running"]}]}
  while next_token is not None:
      response = boto3.client("ec2").describe_instances(**kwargs)
      next_token = response.get('NextToken', None)
      result += jmespath.search("Reservations[].Instances[].{instance_id: InstanceId, value: `1`}", response)
      kwargs["NextToken"] = next_token  
```

The dict values returned by the paginator or service method are then converted by this module into `GaugeMetricFamily` samples.
Each dict must have the same keys as `label_names`, plus an additional `value` key; the corresponding values correspond to the labels and value of the created Gauge, respectively.

Note that `pagninator_args` may be a string. In that case, it will be `eval`-ed with access to `datetime.datetime` and `datetime.timedelta`. For example:

```yaml
recent_emr_cluster_ids:
  description: Recent EMR cluster ids
  service: emr
  paginator: list_clusters
  paginator_args: |
    {
        "CreatedAfter": datetime.now() - timedelta(weeks=4)
    }
  label_names:
    - id
  search: |
    Clusters[].{id: Id, value: `1`}
```

## Example Usage

The module can be run directly, as follows:

```bash
python -m aws_prometheus_exporter --metrics-file ./metrics.yaml --port 9000 --period-seconds 300
```

Running using Docker:

```bash
docker build -t aws_prometheus_exporter:latest  .
docker run -p9000:9000 -v $(pwd)/example.yaml:/mnt/metrics.yaml aws_prometheus_exporter
```

Alternatively, you can import the module into an existing application. See `__main__.py` for an example.

## Links

* Boto3 docs: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
* Boto3 paginator docs: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/paginators.html
* Prometheus: https://prometheus.io/
* Prometheus Python Client: https://github.com/prometheus/client_python
