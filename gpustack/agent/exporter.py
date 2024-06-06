from prometheus_client.registry import Collector
from prometheus_client import make_asgi_app, REGISTRY
from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily
from gpustack.agent.collector import NodeStatusCollector
import uvicorn
import logging
from fastapi import FastAPI

logger = logging.getLogger(__name__)


class MetricExporter(Collector):
    _provider = "gpustack"

    def __init__(self, node_ip: str, port: int):
        self._node_ip = node_ip
        self._collector = NodeStatusCollector(node_ip)
        self._port = port

    def collect(self):  # noqa: C901
        labels = ["instance", "provider"]
        filesystem_labels = ["instance", "provider", "mountpoint"]
        gpu_labels = ["instance", "provider", "index"]

        # metrics
        os_info = InfoMetricFamily("node_os", "Operating system information")
        kernel_info = InfoMetricFamily("node_kernel", "Kernel information")
        uptime = GaugeMetricFamily(
            "node_uptime_seconds", "Uptime in seconds of the node", labels=labels
        )
        cpu_cores = GaugeMetricFamily(
            "node_cpu_cores", "Total CPUs cores of the node", labels=labels
        )
        cpu_utilization_rate = GaugeMetricFamily(
            "node_cpu_utilization_rate",
            "Rate of CPU utilization on the node",
            labels=labels,
        )
        memory_total = GaugeMetricFamily(
            "node_memory_total_bytes",
            "Total memory in bytes of the node",
            labels=labels,
        )
        memory_used = GaugeMetricFamily(
            "node_memory_used_bytes", "Memory used in bytes of the node", labels=labels
        )
        memory_utilization_rate = GaugeMetricFamily(
            "node_memory_utilization_rate",
            "Rate of memory utilization on the node",
            labels=labels,
        )
        gpu_info = InfoMetricFamily("node_gpu", "GPU information")
        gpu_cores = GaugeMetricFamily(
            "node_gpu_cores", "Total GPUs cores of the node", labels=gpu_labels
        )
        gpu_utilization_rate = GaugeMetricFamily(
            "node_gpu_utilization_rate",
            "Rate of GPU utilization on the node",
            labels=gpu_labels,
        )
        gpu_temperature = GaugeMetricFamily(
            "node_gpu_temperature_celsius",
            "GPU temperature in celsius of the node",
            labels=gpu_labels,
        )
        gram_total = GaugeMetricFamily(
            "node_gram_total_bytes",
            "Total GPU RAM in bytes of the node",
            labels=gpu_labels,
        )
        gram_used = GaugeMetricFamily(
            "node_gram_used_bytes",
            "GPU RAM used in bytes of the node",
            labels=gpu_labels,
        )
        gram_utilization_rate = GaugeMetricFamily(
            "node_gram_utilization_rate",
            "Rate of GPU RAM utilization on the node",
            labels=gpu_labels,
        )
        filesystem_total = GaugeMetricFamily(
            "node_filesystem_total_bytes",
            "Total filesystem in bytes of the node",
            labels=filesystem_labels,
        )
        filesystem_used = GaugeMetricFamily(
            "node_filesystem_used_bytes",
            "Total filesystem used in bytes of the node",
            labels=filesystem_labels,
        )
        filesystem_utilization_rate = GaugeMetricFamily(
            "node_filesystem_utilization_rate",
            "Rate of filesystem utilization on the node",
            labels=filesystem_labels,
        )

        node = self._collector.collect().status
        if node is None:
            logger.error("Failed to get node status.")
            return

        # system
        if node.os is not None:
            os_info.add_metric(
                ["instance", "provider", "name", "version"],
                {
                    "instance": self._node_ip,
                    "provider": self._provider,
                    "name": node.os.name,
                    "version": node.os.version,
                },
            )

        # kernel
        if node.kernel is not None:
            kernel_info.add_metric(
                ["instance", "provider", "name", "version"],
                {
                    "instance": self._node_ip,
                    "provider": self._provider,
                    "name": node.kernel.name,
                    "release": node.kernel.release,
                    "version": node.os.version,
                    "architecture": node.kernel.architecture,
                },
            )

        # uptime
        if node.uptime is not None:
            uptime.add_metric([self._node_ip, self._provider], node.uptime.uptime)

        # cpu
        if node.cpu is not None:
            cpu_cores.add_metric([self._node_ip, self._provider], node.cpu.total)
            cpu_utilization_rate.add_metric(
                [self._node_ip, self._provider], node.cpu.utilization_rate
            )

        # memory
        if node.memory is not None:
            memory_total.add_metric([self._node_ip, self._provider], node.memory.total)
            memory_used.add_metric([self._node_ip, self._provider], node.memory.used)
            memory_utilization_rate.add_metric(
                [self._node_ip, self._provider],
                _rate(node.memory.used, node.memory.total),
            )

        # gpu
        if node.gpu is not None:
            for i, d in enumerate(node.gpu):
                gpu_info.add_metric(
                    ["instance", "provider", "index", "name"],
                    {
                        "instance": self._node_ip,
                        "provider": self._provider,
                        "index": str(i),
                        "name": d.name,
                    },
                )
                gpu_cores.add_metric(
                    [self._node_ip, self._provider, str(i)], d.core_total
                )
                gpu_utilization_rate.add_metric(
                    [self._node_ip, self._provider, str(i)], d.core_utilization_rate
                )
                gpu_temperature.add_metric(
                    [self._node_ip, self._provider, str(i)], d.temperature
                )
                gram_total.add_metric(
                    [self._node_ip, self._provider, str(i)], d.memory_total
                )
                gram_used.add_metric(
                    [self._node_ip, self._provider, str(i)], d.memory_used
                )
                gram_utilization_rate.add_metric(
                    [self._node_ip, self._provider, str(i)],
                    _rate(d.memory_used, d.memory_total),
                )

        # filesystem
        if node.filesystem is not None:
            for _, d in enumerate(node.filesystem):
                filesystem_total.add_metric(
                    [self._node_ip, self._provider, d.mount_point], d.total
                )
                filesystem_used.add_metric(
                    [self._node_ip, self._provider, d.mount_point], d.used
                )
                filesystem_utilization_rate.add_metric(
                    [self._node_ip, self._provider, d.mount_point],
                    _rate(d.used, d.total),
                )

        # system
        yield os_info
        yield kernel_info
        yield uptime
        yield cpu_cores
        yield cpu_utilization_rate
        yield memory_total
        yield memory_used
        yield memory_utilization_rate
        yield gpu_info
        yield gpu_cores
        yield gpu_utilization_rate
        yield gpu_temperature
        yield gram_total
        yield gram_used
        yield gram_utilization_rate
        yield filesystem_total
        yield filesystem_used
        yield filesystem_utilization_rate

    async def start(self):
        REGISTRY.register(self)

        # Start FastAPI server
        metrics_app = make_asgi_app()

        app = FastAPI(title="GPUStack Agent", response_model_exclude_unset=True)
        app.mount("/metrics", metrics_app)

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self._port,
            access_log=False,
            log_level="error",
        )

        logger.info(f"Serving on {config.host}:{config.port}.")
        server = uvicorn.Server(config)
        await server.serve()


def _rate(used, total):
    return round(used / total, 6) * 100