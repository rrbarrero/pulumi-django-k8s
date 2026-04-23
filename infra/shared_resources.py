import pulumi_kubernetes as k8s

from common import (
    TRAEFIK_HTTP_NODE_PORT,
    TRAEFIK_HTTPS_NODE_PORT,
    TRAEFIK_INGRESS_CLASS,
    TRAEFIK_NAME,
    TRAEFIK_NAMESPACE,
)


def create_traefik() -> k8s.helm.v3.Release:
    return k8s.helm.v3.Release(
        TRAEFIK_NAME,
        name=TRAEFIK_NAME,
        chart=TRAEFIK_NAME,
        repository_opts={
            "repo": "https://traefik.github.io/charts",
        },
        namespace=TRAEFIK_NAMESPACE,
        create_namespace=True,
        values={
            "service": {
                "type": "NodePort",
            },
            "ingressClass": {
                "enabled": True,
                "isDefaultClass": False,
                "name": TRAEFIK_INGRESS_CLASS,
            },
            "ports": {
                "web": {
                    "nodePort": TRAEFIK_HTTP_NODE_PORT,
                },
                "websecure": {
                    "nodePort": TRAEFIK_HTTPS_NODE_PORT,
                },
            },
            "providers": {
                "kubernetesIngress": {
                    "ingressClass": TRAEFIK_INGRESS_CLASS,
                },
                "kubernetesCRD": {
                    "ingressClass": TRAEFIK_INGRESS_CLASS,
                },
            },
        },
    )
