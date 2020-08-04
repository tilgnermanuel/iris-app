##  A Simple CI/CD Pipeline with Jenkins und Kubernetes

### Introduction

In this tutorial we set up a simple CI/CD Pipeline for a Flask app using Jenkins und Google Kubernetes Engine (GKE) in three steps. First, we containerize the app to prepare it for deployment. Second, we set up a Kubernetes cluster and install Jenkins. Third, we build a Jenkins pipeline and run it. The goal is to have our app running on GKE as an API. Whenever we make changes to the app code, the new version of the app should automatically be deployed.

Our starting point is a Flask-based API written by my colleague Jannik. His API exposes a K-Nearest Neighbor (KNN) model that provides predictions based on the iris dataset. Turning a model into an API is a quick way to make it available to others. People can send an HTTP request to the API with measurements (petal_length=4) and get a response ("This most likely belongs to the species Setosa"). If you're curious, check out [Jannik's post](https://www.statworx.com/de/blog/how-to-build-a-machine-learning-api-with-python-and-flask/) to learn more. 

Our objective is to set up a Jenkins pipeline which deploys this API to Kubernetes. Jenkins and Kubernetes can be daunting when first starting out. My hope is to give you a better understanding of the these tools and provide you with a template that you can tweak for your deployments. This tutorial is geared towards a deployment on Google Cloud Platform (GCP) and uses auxiliary services such as Cloud Source Repositories, Cloud Build and Cloud Container Registry.

Note: The post uses Flask app, app und API interchangeably. 

### Dockerizing the app

For this step, I assume that you already have a Flask app. If not, just copy the one from our GitHub repo. It's mostly based on Jannik's app with a few changes for the purposes of this tutorial. 

```bash
git clone https://...
```

Once you have the app, we containerize it with Docker. For this we create a Dockerfile. To keep the image small, we use the `python:3.7-slim` base image. Then we create a new directory in the container and copy our app code including the Python package requirements. Using pip, we install all required packages. Finally, we expose the container on port 8080 and specify the start-up command. 

Done! For an app as simple as ours, that's all we need to do.

### What is CI/CD?

CI/CD stands for Continuous Integration/Continuous Delivery. Continuous integration means developers integrate their code changes with high frequency. Continuous development means code is pushed out to production on a regular basis, multiple times a day. Both concepts often go together. 

Here we build a CI/CD pipeline which is nothing more that a series of steps taking code from a version control system to a target environment.

### What is Kubernetes?

Kubernetes is an open-source container orchestration platform for deploying, managing and scaling containerized applications, workflows and services. Google Kubernetes Engine is simply a hosted version of Kubernetes.

### What is Jenkins? 

Jenkins is an open-source tool that automates the process of building, testing and deploying software.

### How to define a Jenkins Pipeline

A Jenkins Pipeline is defined with a Jenkinsfile and consists of one or more stages. Each stage must be completed for the entire pipeline to succeed. 

The Pipeline we use to deploy our app has three stages: `Build`, `Test` and `Deploy`. Each stage is executed in a different container. It is good practice to have a stages run in a clean environment that contains all required  dependencies.

The `Build` stage uses the `gcloud` container to build an image from our Dockerfile and save it to GCP's Container Registry. The image tag is dynamic: its version number corresponds to the build number, an environment variable that is available per default in Jenkins.

The `Test`stage uses the image that we just built and tests it using `pytest`. Does our API work? If our test passes, the stage is successful and we move on to the next stage.

The `Deploy`stage deploys the app to the Kubernetes cluster. This requires Kubernetes manifest files for the deployment and the load balancer. How to define these files is beyond the scope of this tutorial however. The Kubernetes homepage provides some great resources however.

A caveat: containers defined in our Kubernetes agent (explained shortly) have to be available from the get-go. In other words, the initial version of our app  (iris-app:v1) must exist in the Container Registry _before_ the pipeline runs for the first time. This is why you once have to build the image manually:

```bash
gcloud builds submit -t gcr.io/sandfox/iris-app:v1
```

Let's break down the Jenkins Pipeline, step by step:

- A declarative pipeline starts with the `pipeline { }` block.
- The `environment` directive defines environment variables for the pipeline. This can be done at the top level, stage level or both. Here, we define environment variables that are valid for all steps at the top level.
- The `agent` section determines where the pipeline or one of its stages runs. It must be defined in the top level pipeline block. Here, we use the Kubernetes agent which runs stages inside a Pod deployed on a Kubernetes cluster. The Pod template is defined within the `kubernetes { }` block using yaml syntax.
- The `stages`section consists of one or more `stage` directives. This is where where most of the action takes place. We have three stages: `Build`, `Test`and `Deploy`. 
- The `steps` section specifies one or more steps to be run in a `stage` directive. In this case, most steps consists of shell commands in the containers specified by the Kubernetes agent.

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

The shell commands are self-explanatory. More interesting here is the Kubernetes Plugin `KubernetesEngineBuilder`. Here are the arguments in turn:

* $class: the Google Kubernetes Engine Builder Plugin
* projectId: the ID of your GCP project (here: sandfox)
* clusterName: the name of your cluster (here: my-cluster)
* manifestPattern: the pattern of the Kubernetes manifest to be deployed
* verifyDeployments: whether to verify the deployments or not

To sum up, our Jenkinsfile defines a Pipeline that will:

1. Check out code from Cloud Source Repository.
2. Build an Docker image of our app based on the Dockerfile.
3. Push the image to Cloud Container Registry.
4. Pull the image to run tests against it.
5. Deploy an instance of the image, i.e. a container, to Google Kubernetes engine as part of an deployment with an associated Load Balancer.

But enough theory. Let's set up our GKE cluster!

### How to set up a Google Kubernetes Engine Cluster

Navigate to the GCP console and open your cloud shell. Start by setting and exporting your project.

```bash
gcloud config set project <YOUR-PROJECT-ID>
export PROJECT=$(gcloud config get-value project)
```

Next, define your preferred compute zone (saves some typing later):

```bash
gcloud config set compute/zone us-central1-a
```

Create a service account for Jenkins:

```bash
gcloud iam service-accounts create jenkins-sa --display-name jenkins
-sa
```

Following the principle of least privilege, give the service account only the permissions that it needs in line with Google's predefined roles.

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

Once you're done, navigate to GCP's "IAM & Admin", then "IAM" and verify that your service account has the required permissions. If all looks good, click on "Service Accounts" and create JSON key from your Jenkins service account that we need later.

Now, create a Google Kubernetes Engine cluster with the service account defined above:

```bash
gcloud container clusters create my-cluster \
  --num-nodes 2 \
  --machine-type n1-standard-2 \
  --cluster-version 1.15 \
  --service-account "jenkins-sa@$PROJECT.iam.gserviceaccount.com"
```

Once the cluster is up and running, fetch the credentials:

```bash
gcloud container clusters get-credentials my-cluster
```

Grant your GCP account cluster admin permissions in the cluster's RBAC. This allows you create cluster role bindings for Jenkins. You find this yaml file under k8s/rbac in the GitHub repository.

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
  name: <YOUR-GCP-E-MAIL-LOGIN>
```

In your home directory, download and install `Helm`, which is the package manager for Kubernetes. We will use  it to install Jenkins with a stable chart.

```bash
cd
wget https://get.helm.sh/helm-v3.2.1-linux-amd64.tar.gz
tar -zxfv helm-v3.2.1-linux-amd64.tar.gz
cd linux-amd64
cp helm ../iris-app && cd ../iris-app
./helm repo add stable https://kubernetes-charts.storage.googleapis.com
```

Create a jenkins-values.yaml file which specifies the plugins we need for the Pipeline. These plugins allow us to use the service account we created to interact with Google APIs.

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

Now, give the Jenkins service account permission to deploy to the cluster:

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

In order to reach the Jenkins UI, you need to set up port forwarding from the Google Cloud Shell:

```bash
export JENKINS_POD=$(kubectl get pods --namespace default -l "app.kubernetes.io/component=jenkins-master" -l "app.kubernetes.io/instance=jenkins-server" -o jsonpath="{.items[0].metadata.name}")
kubectl port-forward $JENKINS_POD 8080:8080
```

In a shell new tab, fetch the Jenkins password:

```bash
printf $(kubectl get secret --namespace default jenkins-server -o jsonpath="{.data.jenkins-admin-password}" | base64 --decode); echo
```

You are now able to log into Jenkins with the username "admin"!

Once logged in, you need to set up your service account credential. For this click on "Manage Jenkins" > "Manage Credentials" > Click on "global" > "Add credentials" > Select "Google Service Account from private Key" > Enter project name and upload your JSON key from the first part of the tutorial.

Now go to Jenkins main page, create a new item, specifically a Multibranch Pipeline and give it the name "iris-app". Add a source git and paste in the https url of your repository. From the credentials dropdown select the credential you just created. 

Finally, set "Scan Multibranch Pipeline Triggers" to periodically if not otherwise run with an Interval of 1 minute. And then sit back and watch as Jenkins deploys your app!