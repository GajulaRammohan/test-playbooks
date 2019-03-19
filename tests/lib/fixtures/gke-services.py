import pytest
import googleapiclient.discovery
import kubernetes.client
import base64
from google.oauth2 import service_account
import fauxfactory


class K8sClient(object):
    def __init__(self, client):
        self.client = client
        self.apps = kubernetes.client.AppsV1Api(self.client)
        self.core = kubernetes.client.CoreV1Api(self.client)
        self.storage = kubernetes.client.StorageV1Api(self.client)
        self.deploymentobject = kubernetes.client.V1Deployment()
        self.serviceobject = kubernetes.client.V1Service()
        self.secretobject = kubernetes.client.V1Secret()
        self.configmapobject = kubernetes.client.V1ConfigMap()

    def generate_deployment(self, prefix, containerspec):
        deployment = self.deploymentobject
        deploymentname = '{}-{}'.format(prefix, fauxfactory.gen_string('alphanumeric', 5)).lower()
        deployment.api_version = 'apps/v1'
        deployment.metadata = {'name': deploymentname,
                               'integration': 'true'}
        deployment.spec = {}
        deployment.spec['selector'] = {'matchLabels': {'run': deploymentname}}
        deployment.spec['template'] = {}
        deployment.spec['template']['metadata'] = {'labels': {'run': deploymentname}}
        deployment.spec['template']['spec'] = {'containers': containerspec}

        return deploymentname, deployment

    def destroy(self, deploymentname):
        self.core.delete_namespaced_service(deploymentname, 'default', body=kubernetes.client.V1DeleteOptions())
        self.apps.delete_namespaced_deployment(deploymentname, 'default', body=kubernetes.client.V1DeleteOptions())


def create_gke_clients():
    def create_clients(credentials):
        sa_creds = service_account.Credentials.from_service_account_info(credentials['cloud']['gke']['serviceaccount']['key'])
        gke = googleapiclient.discovery.build('container', 'v1', credentials=sa_creds)
        name = credentials['cloud']['gke']['cluster']
        gke_clusters = gke.projects().locations().clusters()
        gke_cluster = gke_clusters.get(name=name).execute()
        kube_config = kubernetes.client.Configuration()
        kube_config.host = 'https://{}'.format(gke_cluster['endpoint'])
        kube_config.verify_ssl = True
        kube_config.api_key['authorization'] = credentials['cloud']['gke']['api_key']
        kube_config.api_key_prefix['authorization'] = 'Bearer'
        kube_config.ssl_ca_cert = '/tmp/ssl_ca_cert'
        with open(kube_config.ssl_ca_cert, 'wb') as f:
            f.write(base64.decodestring(gke_cluster['masterAuth']['clusterCaCertificate'].encode()))
        client = kubernetes.client.ApiClient(configuration=kube_config)
        return K8sClient(client)
    return create_clients


@pytest.fixture
def gke_client_fscope():
    return create_gke_clients()


@pytest.fixture(scope='class')
def gke_client_cscope():
    return create_gke_clients()
