from django.http import JsonResponse
from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException


def _load_kubernetes_config():
    try:
        config.load_incluster_config()
        return "in-cluster"
    except ConfigException:
        config.load_kube_config()
        return "kubeconfig"


def main(request):
    try:
        config_source = _load_kubernetes_config()
        v1 = client.CoreV1Api()
        pods = v1.list_pod_for_all_namespaces(watch=False)
    except ConfigException as exc:
        return JsonResponse(
            {
                "error": "Kubernetes configuration is not available.",
                "details": str(exc),
            },
            status=503,
        )
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Failed to query the Kubernetes API.",
                "details": str(exc),
            },
            status=502,
        )

    return JsonResponse(
        {
            "config_source": config_source,
            "pods": [
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "ip": pod.status.pod_ip,
                }
                for pod in pods.items
            ],
        }
    )
