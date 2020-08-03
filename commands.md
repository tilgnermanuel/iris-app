##  A Simple CI/CD Pipeline with Jenkins und Kubernetes

### Introduction

This tutorial walks you through the steps of setting up a simple CI/CD Pipeline using Jenkins und Google Kubernetes Engine (GKE). We start by packaging a Flask app in a Docker container to prepare it for deployment. Next we set up a Kubernetes cluster and install Jenkins. As a final step, we build a Jenkins pipeline and run it. The goal is to host a web service, concretely an API on GKE for public access.

Our starting point is a Flask-based API written by my colleague Jannik. This API exposes a K-Nearest Neighbor (KNN) model that provides predictions based on the iris dataset. By turning a model into an API, you can make it available to others. People can then send an HTTP request to the API with measurements (petal length=4) and get a response ("This most likely is the species Setosa"). If you're curious, check out [Jannik's post](https://www.statworx.com/de/blog/how-to-build-a-machine-learning-api-with-python-and-flask/) to learn more. 

Today I want to show you how to take this API and integrate into a CI/CD pipeline using Jenkins which deploys to Kubernetes. Both tools can be daunting, especially if you're just starting out deploying your models. My hope is to give you a better understanding of the these tools as a well as a simple template that you can tweak for your deployments.

### Dockerizing the app

For this step I assume that you already have a Flask app (I use the words Flask app, app und API interchangeably here). If not, you can just use the one from my GitHub repo. It's mostly based on Jannik's app with some small modifications for the purposes of this tutorial. 

```bash
git clone https://...
```

Once you have the app, we can containerize it with Docker. For this we create a Dockerfile. To keep the image small, we use the `python:3.7-slim` base image. Then we create a new directory in the container and copy our app code including the Python package requirements. Using pip, we install all required packages. At last, we expose the container on port 8080 and specify the start-up command. And done! For an app as simple as ours, that's all we need to do.

### CI/CD 

CI/CD stands for Continuous Integration/Continuous Delivery. Continuous integration means developers integrate their code changes with high frequency. Continuous development means code is pushed out to production on a regular basis, multiple times a day. Both concepts often go together. 

Here we build a CI/CD pipeline which is nothing more that a series of steps taking code from a version control system to a target environment.

### Jenkins

Jenkins is an open-source tool which allows you to automate the process of building, testing and deploying applications to different environments (e.g. Kubernetes). A Jenkins Pipeline is specified with the help of a so-called Jenkinsfile and consists of one or more stages. Each stage must be completed for the pipeline to succeed. 

Below is the pipeline that we use to deploy our app on GKE. It has three stages: `Build`, `Test` and `Deploy`. Each stage is executed in a different container. It is good practice to have a stage run in a container which contains all dependencies that the stage requires.

The `Build` stage uses the `gcloud` to build an image from our Dockerfile and save it to GCP's Container Registry. The image tag in this case is dynamic: its version number corresponds to the build number, an environment variable that is available per default in Jenkins.

The `Test`stage uses the image that we just built and tests it using `pytest`. Does our API work? If our test passes, the stage is successful and we move on. A

The `Deploy`stage at last deploys the app to the Kubernetes cluster running with GKE. This requires deployment and service manifest file. How to define these files is beyond the scope of this tutorial. A good starting point is the Kubernetes homepage.

If you're following along, note that pods / containers defined in our Kubernetes manifest have to be runnable from the get-go. That is, the initial version of our app  (iris-app:v1) must exist in the Container Registry _before_ the pipeline runs for the first time. This is why prior to triggering the pipeline, you once have to build the image manually:

```bash
gcloud builds submit -t gcr.io/sandfox/iris-app:v1
```

Important here is the Kubernetes Plugin `KubernetesEngineBuilder`. Here are the arguments in turn:

* $class: the Google Kubernetes Engine Builder Plugin
* projectId: the ID of your GCP project (here: sandfox)
* clusterName: the name of your cluster (here: my-cluster)
* manifestPattern: the pattern of the Kubernetes manifest to be deployed
* verifyDeployments: whether to verify the deployments or not

```groovy
pipeline {
  environment {
    PROJECT = "sandfox"
    APP_NAME = "iris-app"
    SVC_NAME = "${APP_NAME}-service"
    CLUSTER = "my-cluster"
    CLUSTER_ZONE = "us-central1-a"
    IMAGE_TAG = "gcr.io/${PROJECT}/${APP_NAME}:v${env.BUILD_NUMBER}"
    JENKINS_CRED = "${PROJECT}"
  }
  agent {
    kubernetes {
      label 'iris-app'
      defaultContainer 'jnlp'
      yaml """
apiVersion: v1
kind: Pod
metadata:
labels:
  component: ci
spec:
  serviceAccountName: jenkins-server
  containers:
  - name: flask
    image: gcr.io/sandfox/iris-app:v1
    command:
    - cat
    tty: true
  - name: gcloud
    image: gcr.io/cloud-builders/gcloud
    command:
    - cat
    tty: true
  - name: kubectl
    image: gcr.io/cloud-builders/kubectl
    command:
    - cat
    tty: true
"""
    }
  }
  stages {
    stage('Build') {
      steps {
        container('gcloud') {
          sh "PYTHONUNBUFFERED=1 gcloud builds submit -t ${IMAGE_TAG} ."
        }
      }
    }
    stage('Test') {
      steps {
        container('flask') {
          sh "python -m pytest test.py"
        }
      }
    }
    stage('Deploy') {
      when { branch 'master' }
      steps{
        container('kubectl') {
          sh("sed -i.bak 's#gcr.io/sandfox/iris-app:v1#${IMAGE_TAG}#' ./k8s/deployments/deployment.yaml")
          step([$class: 'KubernetesEngineBuilder', projectId: env.PROJECT, clusterName: env.CLUSTER, zone: env.CLUSTER_ZONE, manifestPattern: 'k8s/services', credentialsId: env.JENKINS_CRED, verifyDeployments: false])
          step([$class: 'KubernetesEngineBuilder', projectId: env.PROJECT, clusterName: env.CLUSTER, zone: env.CLUSTER_ZONE, manifestPattern: 'k8s/deployments', credentialsId: env.JENKINS_CRED, verifyDeployments: true])
          sh("echo http://`kubectl get service/${SVC_NAME} -o jsonpath='{.status.loadBalancer.ingress[0].ip}'` > ${SVC_NAME}")
        }
      }
    }
  }
}
```

Let's go through the other sections in turn:

- A declarative pipeline starts with the `pipeline { }` block at the top-level.
- In the `environment` directive we define environment variables for the pipeline. This can be done at the top level, stage level or both. In our case, we define variables like the the project id, cluster name and image tag.
- The `agent` section determines where the pipeline or one of its stages runs. It must be defined in the top-level pipeline block. It can moreover be defined in a stage block. Here, we use the Kubernetes agent. With the Kubernetes agent, individual stages of the pipeline run inside a pod deployed on a Kubernetes cluster. The pod template is defined within the `kubernetes { }` block. 
- The `stages`section consists of one or more `stage` directives which is where most of the action takes place.
- The `steps` section specifies one or more steps to be executed in a `stage` directive. In our case, this consists mostly of running shell commands the containers specified in the Kubernetes yaml.

### How to set up a Google Kubernetes Engine Cluster

Set your compute zone:

```bash
gcloud config set compute/zone us-central1-a
```

Export your project as an environment variable:

```bash
gcloud config set project sandfox
export PROJECT=$(gcloud config get-value project)
```

Create a service account for Jenkins:

```bash
gcloud iam service-accounts create jenkins-sa --display-name jenkins
-sa
```

This follows the principle of least privilege.

Give the service account specific permissions according to Google's predefined roles.

```bash
gcloud projects add-iam-policy-binding $PROJECT \
    --member "serviceAccount:jenkins-sa@$PROJECT.iam.gserviceaccount.com" \
    --role "roles/viewer"

gcloud projects add-iam-policy-binding $PROJECT \
    --member "serviceAccount:jenkins-sa@$PROJECT.iam.gserviceaccount.com" \
    --role "roles/source.reader"

gcloud projects add-iam-policy-binding $PROJECT \
    --member "serviceAccount:jenkins-sa@$PROJECT.iam.gserviceaccount.com" \
    --role "roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT \
    --member "serviceAccount:jenkins-sa@$PROJECT.iam.gserviceaccount.com" \
    --role "roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding $PROJECT \
    --member "serviceAccount:jenkins-sa@$PROJECT.iam.gserviceaccount.com" \
    --role "roles/cloudbuild.builds.editor"

gcloud projects add-iam-policy-binding $PROJECT \
    --member "serviceAccount:jenkins-sa@$PROJECT.iam.gserviceaccount.com" \
    --role "roles/container.developer"
```

Navigate to your Google Cloud Console's IAM page to ensure that the service account got all required permissions.

Create a mini Google Kubernetes Cluster:

```bash
gcloud container clusters create my-cluster \
  --num-nodes 2 \
  --machine-type n1-standard-2 \
  --cluster-version 1.15 \
  --service-account "jenkins-sa@$PROJECT.iam.gserviceaccount.com"
```

Fetch the credentials of your newly created cluster:

```bash
gcloud container clusters get-credentials my-cluster
```

Grant your GCP login account cluster admin permissions in the cluster's RBAC. This allows you create cluster role bindings for Jenkins later.

```yaml
# cluster-admin-binding.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cluster-admin-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
- apiGroup: rbac.authorization.k8s.io
  kind: User
  name: tilgner.manuel@gmail.com
```

Download and install `Helm`, the package manager for Kubernetes that allows you to deploy complex applications in a few steps. For this we install the helm binary and add the official stable repository.

```bash
wget https://get.helm.sh/helm-v3.2.1-linux-amd64.tar.gz
tar -zxfv helm-v3.2.1-linux-amd64.tar.gz
cp linux-amd64/helm .
./helm repo add stable https://kubernetes-charts.storage.googleapis.com
```

Create a values file which contains the Jenkins plugins we need for this pipeline to work. These plugins allow us among others to use the service account we created to access and modify Google Cloud resources.

```yaml
master:
  installPlugins:
    - kubernetes:latest
    - workflow-job:latest
    - workflow-aggregator:latest
    - credentials-binding:latest
    - git:latest
    - google-oauth-plugin:latest
    - google-source-plugin:latest
    - google-kubernetes-engine:latest
    - google-storage-plugin:latest
  resources:
    requests:
      cpu: "50m"
      memory: "1024Mi"
    limits:
      cpu: "1"
      memory: "3500Mi"
  javaOpts: "-Xms3500m -Xmx3500m"
  serviceType: ClusterIP
agent:
  resources:
    requests:
      cpu: "500m"
      memory: "256Mi"
    limits:
      cpu: "1"
      memory: "512Mi"
persistence:
  size: 100Gi
serviceAccount:
  name: jenkins-server
```

Install Jenkins on Kubernetes with the following command:

```bash
./helm install jenkins-server -f jenkins-values.yaml stable/jenkins --version 1.7.3 --wait
```

Give the Jenkins service account permissions to deploy to the cluster:

```bash
# jenkins-cluster-admin-binding.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: jenkins-cluster-admin-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
- kind: ServiceAccount
  name: jenkins-server
  namespace: default
```

Set up port forwarding from the Google Cloud Shell:

```bash
export JENKINS_POD=$(kubectl get pods --namespace default -l "app.kubernetes.io/component=jenkins-master" -l "app.kubernetes.io/instance=jenkins-server" -o jsonpath="{.items[0].metadata.name}")
kubectl port-forward $JENKINS_POD 8080:8080
```

In a new tab, fetch the Jenkins password:

```bash
printf $(kubectl get secret --namespace default jenkins-server -o jsonpath="{.data.jenkins-admin-password}" | base64 --decode); echo
```

Set up a GCP source repository:

```bash
git init
gcloud source repos create setosa
git config --global credential.https://source.developers.google.com.helper gcloud.sh
git remote add google https://source.developers.google.com/p/sandfox/r/setosa
git push --all google
```

Note that if Jenkins is still searching for the next available executor, it could be the case that your machines are under provisioned or that something in your Jenkinsfile is wrong, e.g. wrong cluster or service account name. Checking the system logs is helpful here.
